from unittest.mock import patch

import pytest


def test_cli_stats_runs(monkeypatch, tmp_path, capsys):
    from pedalpoint.cli import main

    monkeypatch.setenv("HOME", str(tmp_path))
    with patch("sys.argv", ["pedalpoint", "stats", "--days", "3"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0
    assert "No handoffs in the last 3 days." in capsys.readouterr().out


def test_cli_stats_reports_handoffs(monkeypatch, tmp_path, capsys):
    from datetime import UTC, datetime

    from pedalpoint import handoff_log
    from pedalpoint.cli import main

    monkeypatch.setenv("HOME", str(tmp_path))
    handoff_log.append(
        {
            "kind": "call",
            "handoff_id": "abc",
            "ts": datetime.now(UTC).isoformat(),
            "model": "m1",
            "backend": "mlx",
            "completion_tokens": 300,
            "changed_tokens": 250,
        }
    )
    with patch("sys.argv", ["pedalpoint", "stats"]):
        with pytest.raises(SystemExit):
            main()
    assert "m1" in capsys.readouterr().out


def test_cli_version(capsys):
    from pedalpoint.cli import main

    with patch("sys.argv", ["pedalpoint", "--version"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("pedalpoint ")


def test_cli_mlx_supervise_passes_args(monkeypatch):
    from pedalpoint import autostart
    from pedalpoint.cli import main

    seen = {}

    def fake(model, port, idle_minutes, mlx_server):
        seen.update(model=model, port=port, idle=idle_minutes, bin=mlx_server)
        return 3

    monkeypatch.setattr(autostart, "run_supervisor", fake)
    monkeypatch.setattr("signal.signal", lambda *a: None)
    argv = [
        "pedalpoint", "mlx-supervise", "--model", "m", "--port", "9000",
        "--idle-minutes", "5", "--mlx-server", "/bin/mlx_lm.server",
    ]
    with patch("sys.argv", argv):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 3
    assert seen == {"model": "m", "port": 9000, "idle": 5, "bin": "/bin/mlx_lm.server"}


def test_cli_mlx_supervise_sigterm_exits_cleanly(monkeypatch):
    import signal

    from pedalpoint import autostart
    from pedalpoint.cli import main

    handlers = {}
    monkeypatch.setattr("signal.signal", lambda sig, h: handlers.__setitem__(sig, h))

    def fake(*_a):
        handlers[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(autostart, "run_supervisor", fake)
    argv = ["pedalpoint", "mlx-supervise", "--model", "m", "--port", "1",
            "--idle-minutes", "1", "--mlx-server", "x"]
    with patch("sys.argv", argv):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0
