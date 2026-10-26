"""Per-backend hints and request tweaks. Both backends speak the OpenAI API."""

from __future__ import annotations

from pedalpoint.config import Config

BACKENDS: tuple[str, ...] = ("mlx", "ollama")


def label(cfg: Config) -> str:
    return {"mlx": "MLX", "ollama": "Ollama"}.get(cfg.backend, cfg.backend)


def start_hint(cfg: Config) -> str:
    if cfg.backend == "mlx":
        return f"mlx_lm.server --model {cfg.model}"
    return "ollama serve"


def pull_hint(cfg: Config, model: str) -> str:
    if cfg.backend == "mlx":
        return f"uvx --from huggingface_hub hf download {model}"
    return f"ollama pull {model}"


def extra_body(cfg: Config) -> dict:
    """Request fields that turn off reasoning/thinking output."""
    if cfg.backend == "mlx":
        return {"chat_template_kwargs": {"enable_thinking": False}}
    if cfg.backend == "ollama":
        return {"reasoning_effort": "none"}
    return {}
