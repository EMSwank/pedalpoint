import dataclasses

from pedalpoint import backends
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
OLLAMA_CFG = dataclasses.replace(
    MLX_CFG, base_url="http://localhost:11434/v1", model="gemma4:12b", backend="ollama"
)
OTHER_CFG = dataclasses.replace(MLX_CFG, backend="lmstudio")


def test_backends_tuple():
    assert backends.BACKENDS == ("mlx", "ollama")


def test_start_hint_mlx():
    assert (
        backends.start_hint(MLX_CFG)
        == "mlx_lm.server --model mlx-community/gemma-4-e4b-it-4bit"
    )


def test_start_hint_ollama():
    assert backends.start_hint(OLLAMA_CFG) == "ollama serve"


def test_pull_hint_mlx():
    assert (
        backends.pull_hint(MLX_CFG, "m/x")
        == "uvx --from huggingface_hub hf download m/x"
    )


def test_pull_hint_ollama():
    assert backends.pull_hint(OLLAMA_CFG, "gemma4:12b") == "ollama pull gemma4:12b"


def test_extra_body_mlx():
    assert backends.extra_body(MLX_CFG) == {
        "chat_template_kwargs": {"enable_thinking": False}
    }


def test_extra_body_ollama():
    assert backends.extra_body(OLLAMA_CFG) == {"reasoning_effort": "none"}


def test_extra_body_unknown():
    assert backends.extra_body(OTHER_CFG) == {}


def test_label():
    assert backends.label(MLX_CFG) == "MLX"
    assert backends.label(OLLAMA_CFG) == "Ollama"
    assert backends.label(OTHER_CFG) == "lmstudio"
