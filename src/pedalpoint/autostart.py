"""Start mlx_lm.server on demand and stop it after an idle period.

Several Claude Code sessions share one model server. They coordinate through
files in ~/.pedalpoint/:

- mlx.last_used      mtime = the last local_llm call from any session
- mlx.start.lock     serializes sessions deciding whether to start a server
- mlx.supervisor.lock held by the supervisor for as long as it runs
- mlx.log            supervisor and mlx_lm.server output

The supervisor is a detached process that owns mlx_lm.server and stops it
once nothing has touched mlx.last_used for `idle_minutes`. A server started
by hand is never stopped: the supervisor only stops its own child.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlparse

from pedalpoint.config import Config

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows: no MLX, no autostart
    fcntl = None  # type: ignore[assignment]

STARTUP_TIMEOUT = 120.0
POLL_SECONDS = 30.0
STOP_GRACE_SECONDS = 15.0
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

Probe = Callable[[], Awaitable[bool]]


def default_state_dir() -> Path:
    return Path.home() / ".pedalpoint"


def port_of(base_url: str) -> int:
    return urlparse(base_url).port or 80


def can_autostart(cfg: Config) -> bool:
    """Only a local MLX server, and only when not switched off."""
    host = urlparse(cfg.base_url).hostname
    return (
        fcntl is not None
        and cfg.backend == "mlx"
        and cfg.autostart
        and host in _LOCAL_HOSTS
    )


def touch_last_used(d: Path) -> None:
    (d / "mlx.last_used").touch()


def idle_seconds(d: Path, now: float) -> float:
    try:
        return now - (d / "mlx.last_used").stat().st_mtime
    except FileNotFoundError:
        return float("inf")


def find_mlx_server() -> str | None:
    """PATH first; ~/.local/bin is where `uv tool install mlx-lm` puts it."""
    found = shutil.which("mlx_lm.server")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "mlx_lm.server"
    return str(local) if os.access(local, os.X_OK) else None


def supervisor_cmd(cfg: Config, mlx_server: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pedalpoint.cli",
        "mlx-supervise",
        "--model",
        cfg.model,
        "--port",
        str(port_of(cfg.base_url)),
        "--idle-minutes",
        str(cfg.idle_minutes),
        "--mlx-server",
        mlx_server,
    ]


def supervisor_running(d: Path) -> bool:
    with open(d / "mlx.supervisor.lock", "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fh, fcntl.LOCK_UN)
        return False


def spawn(cmd: list[str], log: Path) -> subprocess.Popen:
    """Start `cmd` in its own session so it outlives this MCP server."""
    with open(log, "a") as out:
        return subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            cwd=log.parent,
            start_new_session=True,
        )


async def ensure_running(
    cfg: Config,
    probe: Probe,
    *,
    state_dir: Path | None = None,
    spawn: Callable[[list[str], Path], object] = spawn,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Mark the server as used; start it first if it is down and we may.

    Returns quietly when the server is down but autostart does not apply, so
    the caller's usual "not reachable" error reaches the skill unchanged.
    """
    d = state_dir or default_state_dir()
    d.mkdir(parents=True, exist_ok=True)
    touch_last_used(d)
    if await probe() or not can_autostart(cfg):
        return
    mlx_server = find_mlx_server()
    if mlx_server is None:
        raise ValueError(
            f"MLX not reachable at {cfg.base_url} and mlx_lm.server not found "
            "— run install.sh or: uv tool install mlx-lm"
        )
    log = d / "mlx.log"
    with open(d / "mlx.start.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        proc = None
        if not supervisor_running(d) and not await probe():
            proc = spawn(supervisor_cmd(cfg, mlx_server), log)
        deadline = clock() + STARTUP_TIMEOUT
        while not await probe():
            if proc is not None and proc.poll() is not None:
                raise ValueError(f"MLX server exited while starting — see {log}")
            if clock() > deadline:
                raise ValueError(
                    f"MLX server did not start within {int(STARTUP_TIMEOUT)}s "
                    f"— see {log}"
                )
            await sleep(1.0)
    touch_last_used(d)


def _stop(child: subprocess.Popen) -> None:
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def run_supervisor(
    model: str,
    port: int,
    idle_minutes: int,
    mlx_server: str,
    *,
    state_dir: Path | None = None,
    popen: Callable[[list[str]], subprocess.Popen] = subprocess.Popen,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.time,
) -> int:
    """Run mlx_lm.server until it has been idle for `idle_minutes`."""
    d = state_dir or default_state_dir()
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "mlx.supervisor.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0  # another supervisor already owns the server
        touch_last_used(d)
        child = popen([mlx_server, "--model", model, "--port", str(port)])
        try:
            while True:
                sleep(POLL_SECONDS)
                if child.poll() is not None:
                    return child.returncode
                if idle_seconds(d, now()) >= idle_minutes * 60:
                    return 0
        finally:
            _stop(child)
