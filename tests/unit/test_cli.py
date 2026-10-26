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
