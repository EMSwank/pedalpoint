"""Unit tests for pedalpoint.doctor — run before implementing doctor.py."""
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from pedalpoint.config import Config, get_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_CFG = Config(
    base_url="http://localhost:11434/v1",
    model="gemma4:e4b",
    mode="hybrid",
    timeout=120.0,
    initial_fallback_minutes=60,
    context_limit=16000,
    api_model="claude-sonnet-4-6",
    api_key=None,
)

BASE_CFG_WITH_KEY = Config(
    base_url="http://localhost:11434/v1",
    model="gemma4:e4b",
    mode="hybrid",
    timeout=120.0,
    initial_fallback_minutes=60,
    context_limit=16000,
    api_model="claude-sonnet-4-6",
    api_key="sk-ant-test",
)

MODELS_RESPONSE = {"data": [{"id": "gemma4:e4b"}, {"id": "llama3"}]}
MODELS_RESPONSE_MISSING = {"data": [{"id": "llama3"}]}


# ---------------------------------------------------------------------------
# check_binary_in_path
# ---------------------------------------------------------------------------


def test_binary_check_passes_when_found():
    from pedalpoint.doctor import check_binary_in_path

    with patch("shutil.which", return_value="/usr/local/bin/pedalpoint"):
        result = check_binary_in_path()
    assert result.status == "PASS"
    assert "PATH" in result.message
    assert result.fix is None


def test_binary_check_fails_when_not_found():
    from pedalpoint.doctor import check_binary_in_path

    with patch("shutil.which", return_value=None):
        result = check_binary_in_path()
    assert result.status == "FAIL"
    assert result.fix is not None
    assert "uv tool install pedalpoint" in result.fix


# ---------------------------------------------------------------------------
# check_ollama_reachable
# ---------------------------------------------------------------------------


@respx.mock
def test_ollama_reachable_passes():
    from pedalpoint.doctor import check_ollama_reachable

    respx.get("http://localhost:11434/v1/models").mock(
        return_value=httpx.Response(200, json=MODELS_RESPONSE)
    )
    result = check_ollama_reachable(BASE_CFG)
    assert result.status == "PASS"
    assert "http://localhost:11434/v1" in result.message
    assert result.fix is None


@respx.mock
def test_ollama_reachable_fails_on_connect_error():
    from pedalpoint.doctor import check_ollama_reachable

    respx.get("http://localhost:11434/v1/models").mock(
        side_effect=httpx.ConnectError("refused")
    )
    result = check_ollama_reachable(BASE_CFG)
    assert result.status == "FAIL"
    assert result.fix is not None
    assert "ollama serve" in result.fix


@respx.mock
def test_ollama_reachable_fails_on_non_200():
    from pedalpoint.doctor import check_ollama_reachable

    respx.get("http://localhost:11434/v1/models").mock(
        return_value=httpx.Response(500, text="error")
    )
    result = check_ollama_reachable(BASE_CFG)
    assert result.status == "FAIL"
    assert result.fix is not None
    assert "ollama serve" in result.fix


# ---------------------------------------------------------------------------
# check_model_available
# ---------------------------------------------------------------------------


@respx.mock
def test_model_check_passes_when_in_list():
    from pedalpoint.doctor import check_model_available

    respx.get("http://localhost:11434/v1/models").mock(
        return_value=httpx.Response(200, json=MODELS_RESPONSE)
    )
    result = check_model_available(BASE_CFG)
    assert result.status == "PASS"
    assert "gemma4:e4b" in result.message
    assert result.fix is None


@respx.mock
def test_model_check_fails_when_not_in_list():
    from pedalpoint.doctor import check_model_available

    respx.get("http://localhost:11434/v1/models").mock(
        return_value=httpx.Response(200, json=MODELS_RESPONSE_MISSING)
    )
    result = check_model_available(BASE_CFG)
    assert result.status == "FAIL"
    assert result.fix is not None
    assert "ollama pull gemma4:e4b" in result.fix


@respx.mock
def test_model_check_fails_when_ollama_unreachable():
    from pedalpoint.doctor import check_model_available

    respx.get("http://localhost:11434/v1/models").mock(
        side_effect=httpx.ConnectError("refused")
    )
    result = check_model_available(BASE_CFG)
    assert result.status == "FAIL"
    assert result.fix is not None
    assert "ollama pull gemma4:e4b" in result.fix


# ---------------------------------------------------------------------------
# check_pedalpoint_dir
# ---------------------------------------------------------------------------


def test_dir_check_creates_when_missing(tmp_path):
    from pedalpoint.doctor import check_pedalpoint_dir

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    with patch("pathlib.Path.home", return_value=fake_home):
        result = check_pedalpoint_dir()
    assert result.status == "PASS"
    assert (fake_home / ".pedalpoint").is_dir()
    assert result.fix is None


def test_dir_check_passes_when_already_exists(tmp_path):
    from pedalpoint.doctor import check_pedalpoint_dir

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".pedalpoint").mkdir()
    with patch("pathlib.Path.home", return_value=fake_home):
        result = check_pedalpoint_dir()
    assert result.status == "PASS"
    assert result.fix is None


# ---------------------------------------------------------------------------
# check_api_key
# ---------------------------------------------------------------------------


def test_api_key_passes_when_set():
    from pedalpoint.doctor import check_api_key

    result = check_api_key(BASE_CFG_WITH_KEY)
    assert result.status == "PASS"
    assert result.fix is None


def test_api_key_warns_when_missing():
    from pedalpoint.doctor import check_api_key

    result = check_api_key(BASE_CFG)
    assert result.status == "WARN"
    assert result.fix is not None
    assert "export ANTHROPIC_API_KEY" in result.fix


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------


def test_format_report_all_pass_returns_exit_0():
    from pedalpoint.doctor import CheckResult, format_report

    results = [
        CheckResult("PASS", "pedalpoint-server in PATH", None),
        CheckResult("PASS", "Ollama reachable at http://localhost:11434/v1", None),
        CheckResult("PASS", "Model gemma4:e4b available", None),
        CheckResult("PASS", "~/.pedalpoint/ exists", None),
        CheckResult("PASS", "ANTHROPIC_API_KEY set", None),
    ]
    text, code = format_report(results)
    assert code == 0
    assert "All checks passed." in text


def test_format_report_warn_only_exit_0():
    from pedalpoint.doctor import CheckResult, format_report

    results = [
        CheckResult("PASS", "pedalpoint-server in PATH", None),
        CheckResult(
            "WARN", "ANTHROPIC_API_KEY not set", "export ANTHROPIC_API_KEY=sk-ant-..."
        ),
    ]
    text, code = format_report(results)
    assert code == 0
    assert "WARN" in text
    assert "export ANTHROPIC_API_KEY" in text


def test_format_report_with_fail_returns_exit_1():
    from pedalpoint.doctor import CheckResult, format_report

    results = [
        CheckResult("PASS", "pedalpoint-server in PATH", None),
        CheckResult("FAIL", "Model gemma4:e4b not available", "ollama pull gemma4:e4b"),
        CheckResult(
            "WARN", "ANTHROPIC_API_KEY not set", "export ANTHROPIC_API_KEY=sk-ant-..."
        ),
    ]
    text, code = format_report(results)
    assert code == 1
    assert "1 check failed" in text
    assert "FAIL" in text
    assert "Fix: ollama pull gemma4:e4b" in text


def test_format_report_multiple_fails():
    from pedalpoint.doctor import CheckResult, format_report

    results = [
        CheckResult(
            "FAIL", "pedalpoint-server not in PATH", "uv tool install pedalpoint"
        ),
        CheckResult("FAIL", "Ollama not reachable", "ollama serve"),
    ]
    text, code = format_report(results)
    assert code == 1
    assert "2 checks failed" in text


def test_format_report_fix_appears_indented_after_fail():
    from pedalpoint.doctor import CheckResult, format_report

    results = [
        CheckResult("FAIL", "Model gemma4:e4b not available", "ollama pull gemma4:e4b"),
    ]
    text, _ = format_report(results)
    lines = text.splitlines()
    fail_line_idx = next(i for i, line in enumerate(lines) if "FAIL" in line)
    fix_line = lines[fail_line_idx + 1]
    assert "Fix:" in fix_line
    assert fix_line.startswith("      ")  # 6 spaces indent


def test_format_report_warn_fix_appears_indented():
    from pedalpoint.doctor import CheckResult, format_report

    results = [
        CheckResult(
            "WARN", "ANTHROPIC_API_KEY not set", "export ANTHROPIC_API_KEY=sk-ant-..."
        ),
    ]
    text, _ = format_report(results)
    lines = text.splitlines()
    warn_line_idx = next(i for i, line in enumerate(lines) if "WARN" in line)
    fix_line = lines[warn_line_idx + 1]
    assert "Fix:" in fix_line


def test_format_report_exact_output_structure():
    """Lock the exact format to match the spec example."""
    from pedalpoint.doctor import CheckResult, format_report

    results = [
        CheckResult("PASS", "pedalpoint-server in PATH", None),
        CheckResult("PASS", "Ollama reachable at http://localhost:11434/v1", None),
        CheckResult("FAIL", "Model gemma4:e4b not available", "ollama pull gemma4:e4b"),
        CheckResult("PASS", "~/.pedalpoint/ exists", None),
        CheckResult(
            "WARN",
            "ANTHROPIC_API_KEY not set (api_fallback tier disabled)",
            "export ANTHROPIC_API_KEY=sk-ant-...",
        ),
    ]
    text, code = format_report(results)
    assert code == 1
    assert "PASS  pedalpoint-server in PATH" in text
    assert "PASS  Ollama reachable at http://localhost:11434/v1" in text
    assert "FAIL  Model gemma4:e4b not available" in text
    assert "      Fix: ollama pull gemma4:e4b" in text
    assert "PASS  ~/.pedalpoint/ exists" in text
    assert "WARN  ANTHROPIC_API_KEY not set (api_fallback tier disabled)" in text
    assert "      Fix: export ANTHROPIC_API_KEY=sk-ant-..." in text
    assert "1 check failed" in text
    assert "pedalpoint doctor" in text


# ---------------------------------------------------------------------------
# run_all — integration of all checks
# ---------------------------------------------------------------------------


@respx.mock
def test_run_all_returns_five_results():
    from pedalpoint.doctor import run_all

    respx.get("http://localhost:11434/v1/models").mock(
        return_value=httpx.Response(200, json=MODELS_RESPONSE)
    )
    with (
        patch("shutil.which", return_value="/usr/bin/pedalpoint"),
        patch("pathlib.Path.home", return_value=Path("/tmp/fake_home_runall")),
    ):
        Path("/tmp/fake_home_runall/.pedalpoint").mkdir(parents=True, exist_ok=True)
        results = run_all(BASE_CFG_WITH_KEY)
    assert len(results) == 5


@respx.mock
def test_run_all_uses_config_base_url():
    """run_all passes cfg.base_url to the ollama checks."""
    from pedalpoint.doctor import run_all

    custom_url = "http://localhost:9999/v1"
    cfg = Config(
        base_url=custom_url,
        model="gemma4:e4b",
        mode="hybrid",
        timeout=120.0,
        initial_fallback_minutes=60,
        context_limit=16000,
        api_model="claude-sonnet-4-6",
        api_key="sk-ant-test",
    )
    respx.get(f"{custom_url}/models").mock(
        return_value=httpx.Response(200, json=MODELS_RESPONSE)
    )
    with (
        patch("shutil.which", return_value="/usr/bin/pedalpoint"),
        patch("pathlib.Path.home", return_value=Path("/tmp/fake_home_url")),
    ):
        Path("/tmp/fake_home_url/.pedalpoint").mkdir(parents=True, exist_ok=True)
        results = run_all(cfg)
    # ollama check should PASS with custom URL
    assert results[1].status == "PASS"


# ---------------------------------------------------------------------------
# run_all with cfg=None — uses get_config()
# ---------------------------------------------------------------------------


@respx.mock
def test_run_all_defaults_to_get_config(monkeypatch):
    """run_all(None) should call get_config() to obtain cfg."""
    from pedalpoint.doctor import run_all

    for key in [
        "PEDALPOINT_BASE_URL",
        "PEDALPOINT_MODEL",
        "PEDALPOINT_MODE",
        "PEDALPOINT_TIMEOUT",
        "PEDALPOINT_INITIAL_FALLBACK_MINUTES",
        "PEDALPOINT_CONTEXT_LIMIT",
        "PEDALPOINT_API_MODEL",
        "ANTHROPIC_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)
    get_config.cache_clear()
    respx.get("http://localhost:11434/v1/models").mock(
        return_value=httpx.Response(200, json=MODELS_RESPONSE)
    )
    with (
        patch("shutil.which", return_value="/usr/bin/pedalpoint"),
        patch("pathlib.Path.home", return_value=Path("/tmp/fake_home_none_cfg")),
    ):
        Path("/tmp/fake_home_none_cfg/.pedalpoint").mkdir(parents=True, exist_ok=True)
        results = run_all()  # no cfg argument — exercises line 119
    get_config.cache_clear()
    assert len(results) == 5


# ---------------------------------------------------------------------------
# cli.py — dispatch tests
# ---------------------------------------------------------------------------


@respx.mock
def test_cli_doctor_subcommand_exits_0_on_all_pass(monkeypatch, tmp_path):
    """CLI doctor command exits 0 when all checks pass."""
    from pedalpoint.cli import main
    from pedalpoint.config import get_config

    for key in [
        "PEDALPOINT_BASE_URL",
        "PEDALPOINT_MODEL",
        "PEDALPOINT_MODE",
        "PEDALPOINT_TIMEOUT",
        "PEDALPOINT_INITIAL_FALLBACK_MINUTES",
        "PEDALPOINT_CONTEXT_LIMIT",
        "PEDALPOINT_API_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_config.cache_clear()

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    respx.get("http://localhost:11434/v1/models").mock(
        return_value=httpx.Response(200, json=MODELS_RESPONSE)
    )
    with (
        patch("shutil.which", return_value="/usr/bin/pedalpoint"),
        patch("pathlib.Path.home", return_value=fake_home),
        patch("sys.argv", ["pedalpoint", "doctor"]),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
    get_config.cache_clear()
    assert exc_info.value.code == 0


@respx.mock
def test_cli_doctor_subcommand_exits_1_on_fail(monkeypatch, tmp_path):
    """CLI doctor command exits 1 when a check fails."""
    from pedalpoint.cli import main
    from pedalpoint.config import get_config

    for key in [
        "PEDALPOINT_BASE_URL",
        "PEDALPOINT_MODEL",
        "PEDALPOINT_TIMEOUT",
        "PEDALPOINT_INITIAL_FALLBACK_MINUTES",
        "PEDALPOINT_CONTEXT_LIMIT",
        "PEDALPOINT_API_MODEL",
        "ANTHROPIC_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("PEDALPOINT_MODE", raising=False)
    get_config.cache_clear()

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    # Ollama returns 500 — FAIL
    respx.get("http://localhost:11434/v1/models").mock(
        return_value=httpx.Response(500, text="error")
    )
    with (
        patch("shutil.which", return_value="/usr/bin/pedalpoint"),
        patch("pathlib.Path.home", return_value=fake_home),
        patch("sys.argv", ["pedalpoint", "doctor"]),
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
    get_config.cache_clear()
    assert exc_info.value.code == 1


def test_cli_no_subcommand_exits_0():
    """CLI with no subcommand prints help and exits 0."""
    from pedalpoint.cli import main

    with (
        patch("sys.argv", ["pedalpoint"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0
