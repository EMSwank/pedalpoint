import os
import platform
from dataclasses import dataclass
from functools import lru_cache

_DEFAULTS = {
    "mlx": ("http://localhost:8080/v1", "mlx-community/gemma-4-e4b-it-4bit"),
    "ollama": ("http://localhost:11434/v1", "gemma4:12b"),
}


@dataclass(frozen=True)
class Config:
    base_url: str
    model: str
    backend: str
    mode: str
    timeout: float
    initial_fallback_minutes: int
    context_limit: int
    api_model: str
    api_key: str | None


def _platform_default_backend() -> str:
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "mlx"
    return "ollama"


def _resolve_backend(base_url: str | None) -> str:
    explicit = os.getenv("PEDALPOINT_BACKEND")
    if explicit:
        return explicit
    if base_url:
        return "ollama" if ":11434" in base_url else "mlx"
    return _platform_default_backend()


@lru_cache(maxsize=1)
def get_config() -> Config:
    base_url = os.getenv("PEDALPOINT_BASE_URL")
    backend = _resolve_backend(base_url)
    default_url, default_model = _DEFAULTS.get(backend, _DEFAULTS["ollama"])
    return Config(
        base_url=base_url or default_url,
        model=os.getenv("PEDALPOINT_MODEL", default_model),
        backend=backend,
        mode=os.getenv("PEDALPOINT_MODE", "hybrid"),
        timeout=float(os.getenv("PEDALPOINT_TIMEOUT", "120")),
        initial_fallback_minutes=int(
            os.getenv("PEDALPOINT_INITIAL_FALLBACK_MINUTES", "60")
        ),
        context_limit=int(os.getenv("PEDALPOINT_CONTEXT_LIMIT", "16000")),
        api_model=os.getenv("PEDALPOINT_API_MODEL", "claude-sonnet-4-6"),
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )
