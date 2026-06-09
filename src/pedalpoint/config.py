import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Config:
    base_url: str
    model: str
    mode: str
    timeout: float
    initial_fallback_minutes: int
    context_limit: int
    api_model: str
    api_key: str | None


@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config(
        base_url=os.getenv("PEDALPOINT_BASE_URL", "http://localhost:11434/v1"),
        model=os.getenv("PEDALPOINT_MODEL", "gemma4:12b"),
        mode=os.getenv("PEDALPOINT_MODE", "hybrid"),
        timeout=float(os.getenv("PEDALPOINT_TIMEOUT", "120")),
        initial_fallback_minutes=int(
            os.getenv("PEDALPOINT_INITIAL_FALLBACK_MINUTES", "60")
        ),
        context_limit=int(os.getenv("PEDALPOINT_CONTEXT_LIMIT", "16000")),
        api_model=os.getenv("PEDALPOINT_API_MODEL", "claude-sonnet-4-6"),
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )
