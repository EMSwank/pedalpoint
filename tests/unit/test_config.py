import pytest

from pedalpoint.config import get_config


def test_defaults(monkeypatch):
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
    cfg = get_config()
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.model == "gemma4:e4b"
    assert cfg.mode == "hybrid"
    assert cfg.timeout == 120.0
    assert cfg.initial_fallback_minutes == 60
    assert cfg.context_limit == 16000
    assert cfg.api_model == "claude-sonnet-4-6"
    assert cfg.api_key is None
    get_config.cache_clear()


def test_custom_base_url(monkeypatch):
    monkeypatch.setenv("PEDALPOINT_BASE_URL", "http://localhost:1234/v1")
    get_config.cache_clear()
    assert get_config().base_url == "http://localhost:1234/v1"
    get_config.cache_clear()


def test_custom_model(monkeypatch):
    monkeypatch.setenv("PEDALPOINT_MODEL", "llama3")
    get_config.cache_clear()
    assert get_config().model == "llama3"
    get_config.cache_clear()


def test_custom_timeout(monkeypatch):
    monkeypatch.setenv("PEDALPOINT_TIMEOUT", "30")
    get_config.cache_clear()
    assert get_config().timeout == 30.0
    get_config.cache_clear()


def test_custom_fallback_minutes(monkeypatch):
    monkeypatch.setenv("PEDALPOINT_INITIAL_FALLBACK_MINUTES", "30")
    get_config.cache_clear()
    assert get_config().initial_fallback_minutes == 30
    get_config.cache_clear()


def test_custom_context_limit(monkeypatch):
    monkeypatch.setenv("PEDALPOINT_CONTEXT_LIMIT", "8000")
    get_config.cache_clear()
    assert get_config().context_limit == 8000
    get_config.cache_clear()


def test_config_is_frozen():
    get_config.cache_clear()
    cfg = get_config()
    with pytest.raises((AttributeError, TypeError)):
        cfg.model = "other"  # type: ignore
    get_config.cache_clear()


def test_api_model_default(monkeypatch):
    monkeypatch.delenv("PEDALPOINT_API_MODEL", raising=False)
    get_config.cache_clear()
    assert get_config().api_model == "claude-sonnet-4-6"
    get_config.cache_clear()


def test_api_model_custom(monkeypatch):
    monkeypatch.setenv("PEDALPOINT_API_MODEL", "claude-opus-4-7")
    get_config.cache_clear()
    assert get_config().api_model == "claude-opus-4-7"
    get_config.cache_clear()


def test_api_key_absent(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_config.cache_clear()
    assert get_config().api_key is None
    get_config.cache_clear()


def test_api_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_config.cache_clear()
    assert get_config().api_key == "sk-ant-test"
    get_config.cache_clear()
