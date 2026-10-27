import dataclasses
import fcntl
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pedalpoint import autostart
from pedalpoint.config import Config

MLX_CFG = Config(
    base_url="http://localhost:8080/v1",
    model="mlx-community/gemma-4-e4b-it-4bit",
    backend="mlx",
    mode="hybrid",
    timeout=120.0,
    initial_fallback_minutes=60,
    context_limit=16000,
    api_model="claude-sonnet-4-6",
    api_key=None,
)


@pytest.fixture
def state(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    return d


@pytest.fixture
def mlx_bin(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(autostart, "find_mlx_server", lambda: "/bin/mlx_lm.server")
    return "/bin/mlx_lm.server"


class Probe:
    """Reports the server down for `down_for` calls, then up."""

    def __init__(self, down_for: int) -> None:
        self.down_for = down_for
        self.calls = 0

    async def __call__(self) -> bool:
        self.calls += 1
        return self.calls > self.down_for


class FakeProc:
    def __init__(self, exits_after: int | None = None, returncode: int = 0) -> None:
        self.polls = 0
        self.exits_after = exits_after
        self.returncode: int | None = None
        self._final = returncode
        self.terminated = False
        self.killed = False
        self.hang_on_wait = False

    def poll(self) -> int | None:
        self.polls += 1
        if self.returncode is None and self.exits_after is not None:
            if self.polls > self.exits_after:
                self.returncode = self._final
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.hang_on_wait and not self.killed:
            raise subprocess.TimeoutExpired("mlx", timeout or 0)
        self.returncode = self.returncode if self.returncode is not None else 0
        return self.returncode


async def _no_sleep(_s: float) -> None:
    return None


# ── can_autostart ────────────────────────────────────────────────────────────


def test_can_autostart_local_mlx() -> None:
    assert autostart.can_autostart(MLX_CFG)
    for host in ("127.0.0.1", "[::1]"):
        cfg = dataclasses.replace(MLX_CFG, base_url=f"http://{host}:8080/v1")
        assert autostart.can_autostart(cfg)


def test_can_autostart_off_for_ollama_remote_or_disabled() -> None:
    assert not autostart.can_autostart(dataclasses.replace(MLX_CFG, backend="ollama"))
    remote = dataclasses.replace(MLX_CFG, base_url="http://gpu-box:8080/v1")
    assert not autostart.can_autostart(remote)
    assert not autostart.can_autostart(dataclasses.replace(MLX_CFG, autostart=False))


def test_port_defaults_when_url_has_none() -> None:
    assert autostart.port_of("http://localhost:8080/v1") == 8080
    assert autostart.port_of("http://localhost/v1") == 80


# ── idle clock ───────────────────────────────────────────────────────────────


def test_idle_seconds_tracks_last_touch(state: Path) -> None:
    autostart.touch_last_used(state)
    stamp = (state / "mlx.last_used").stat().st_mtime
    assert autostart.idle_seconds(state, stamp + 90) == pytest.approx(90)


def test_idle_seconds_missing_file_is_infinite(state: Path) -> None:
    assert autostart.idle_seconds(state, 0) == float("inf")


# ── find_mlx_server ──────────────────────────────────────────────────────────


def test_find_mlx_server_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart.shutil, "which", lambda _n: "/usr/bin/mlx_lm.server")
    assert autostart.find_mlx_server() == "/usr/bin/mlx_lm.server"


def test_find_mlx_server_falls_back_to_local_bin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(autostart.shutil, "which", lambda _n: None)
    assert autostart.find_mlx_server() is None
    local = Path.home() / ".local" / "bin" / "mlx_lm.server"
    local.parent.mkdir(parents=True)
    local.write_text("#!/bin/sh\n")
    local.chmod(0o755)
    assert autostart.find_mlx_server() == str(local)


# ── supervisor command / lock ────────────────────────────────────────────────


def test_supervisor_cmd() -> None:
    cmd = autostart.supervisor_cmd(MLX_CFG, "/bin/mlx_lm.server")
    assert cmd == [
        sys.executable, "-m", "pedalpoint.cli", "mlx-supervise",
        "--model", "mlx-community/gemma-4-e4b-it-4bit",
        "--port", "8080",
        "--idle-minutes", "20",
        "--mlx-server", "/bin/mlx_lm.server",
    ]


def test_supervisor_running_reflects_lock(state: Path) -> None:
    assert not autostart.supervisor_running(state)
    with open(state / "mlx.supervisor.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert autostart.supervisor_running(state)
    assert not autostart.supervisor_running(state)


def test_spawn_detaches_and_logs(state: Path) -> None:
    code = "import os; print(os.getsid(0) == os.getpid(), os.getcwd())"
    proc = autostart.spawn([sys.executable, "-c", code], state / "mlx.log")
    proc.wait(timeout=10)
    detached, cwd = (state / "mlx.log").read_text().split()
    assert detached == "True"
    assert Path(cwd).resolve() == state.resolve()


# ── ensure_running ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_running_already_up_touches_and_never_spawns(state: Path) -> None:
    spawned: list = []
    await autostart.ensure_running(
        MLX_CFG, Probe(0), state_dir=state, spawn=lambda *a: spawned.append(a)
    )
    assert spawned == []
    assert (state / "mlx.last_used").exists()


@pytest.mark.asyncio
async def test_ensure_running_not_autostartable_returns_quietly(state: Path) -> None:
    spawned: list = []
    cfg = dataclasses.replace(MLX_CFG, autostart=False)
    await autostart.ensure_running(
        cfg, Probe(99), state_dir=state, spawn=lambda *a: spawned.append(a)
    )
    assert spawned == []


@pytest.mark.asyncio
async def test_ensure_running_spawns_supervisor_and_waits(
    state: Path, mlx_bin: str
) -> None:
    spawned: list = []

    def spawn(cmd: list[str], log: Path) -> FakeProc:
        spawned.append((cmd, log))
        return FakeProc()

    probe = Probe(3)
    await autostart.ensure_running(
        MLX_CFG, probe, state_dir=state, spawn=spawn, sleep=_no_sleep
    )
    assert len(spawned) == 1
    cmd, log = spawned[0]
    assert cmd == autostart.supervisor_cmd(MLX_CFG, mlx_bin)
    assert log == state / "mlx.log"
    assert probe.calls == 4


@pytest.mark.asyncio
async def test_ensure_running_waits_on_existing_supervisor(
    state: Path, mlx_bin: str
) -> None:
    spawned: list = []
    with open(state / "mlx.supervisor.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        await autostart.ensure_running(
            MLX_CFG,
            Probe(2),
            state_dir=state,
            spawn=lambda *a: spawned.append(a),
            sleep=_no_sleep,
        )
    assert spawned == []


@pytest.mark.asyncio
async def test_ensure_running_missing_binary(
    state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(autostart, "find_mlx_server", lambda: None)
    with pytest.raises(ValueError, match="mlx_lm.server not found"):
        await autostart.ensure_running(MLX_CFG, Probe(99), state_dir=state)


@pytest.mark.asyncio
async def test_ensure_running_supervisor_exits_early(state: Path, mlx_bin: str) -> None:
    with pytest.raises(ValueError, match="exited while starting.*mlx.log"):
        await autostart.ensure_running(
            MLX_CFG,
            Probe(99),
            state_dir=state,
            spawn=lambda *a: FakeProc(exits_after=1, returncode=1),
            sleep=_no_sleep,
        )


@pytest.mark.asyncio
async def test_ensure_running_times_out(state: Path, mlx_bin: str) -> None:
    ticks = iter(range(0, 10_000, 50))
    with pytest.raises(ValueError, match="did not start within 120s"):
        await autostart.ensure_running(
            MLX_CFG,
            Probe(99),
            state_dir=state,
            spawn=lambda *a: FakeProc(),
            sleep=_no_sleep,
            clock=lambda: next(ticks),
        )


# ── run_supervisor ───────────────────────────────────────────────────────────


def _clock(state: Path, idle_after: float):
    """now() that reads as `idle_after` seconds past the last touch."""

    def now() -> float:
        return (state / "mlx.last_used").stat().st_mtime + idle_after

    return now


def test_supervisor_stops_child_when_idle(state: Path) -> None:
    child = FakeProc()
    started: list = []

    def popen(cmd: list[str]) -> FakeProc:
        started.append(cmd)
        return child

    code = autostart.run_supervisor(
        "m", 8080, 20, "/bin/mlx_lm.server",
        state_dir=state, popen=popen, sleep=lambda _s: None,
        now=_clock(state, 20 * 60),
    )
    assert code == 0
    assert started == [["/bin/mlx_lm.server", "--model", "m", "--port", "8080"]]
    assert child.terminated and not child.killed
    assert not autostart.supervisor_running(state)


def test_supervisor_keeps_child_while_active(state: Path) -> None:
    child = FakeProc(exits_after=3, returncode=7)
    code = autostart.run_supervisor(
        "m", 8080, 20, "/bin/mlx_lm.server",
        state_dir=state, popen=lambda _c: child, sleep=lambda _s: None,
        now=_clock(state, 60),
    )
    assert code == 7
    assert not child.terminated


def test_supervisor_kills_child_that_ignores_terminate(state: Path) -> None:
    child = FakeProc()
    child.hang_on_wait = True
    autostart.run_supervisor(
        "m", 8080, 20, "/bin/mlx_lm.server",
        state_dir=state, popen=lambda _c: child, sleep=lambda _s: None,
        now=_clock(state, 21 * 60),
    )
    assert child.terminated and child.killed


def test_supervisor_stops_child_on_error(state: Path) -> None:
    child = FakeProc()

    def boom(_s: float) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        autostart.run_supervisor(
            "m", 8080, 20, "/bin/mlx_lm.server",
            state_dir=state, popen=lambda _c: child, sleep=boom,
        )
    assert child.terminated


def test_second_supervisor_exits_without_starting(state: Path) -> None:
    started: list = []
    with open(state / "mlx.supervisor.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        code = autostart.run_supervisor(
            "m", 8080, 20, "/bin/mlx_lm.server",
            state_dir=state, popen=lambda c: started.append(c),
        )
    assert code == 0
    assert started == []


def test_default_state_dir_is_home_pedalpoint() -> None:
    assert autostart.default_state_dir() == Path(os.environ["HOME"]) / ".pedalpoint"


def test_no_autostart_without_fcntl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart, "fcntl", None)
    assert not autostart.can_autostart(MLX_CFG)
