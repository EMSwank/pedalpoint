import ast
import os
from pathlib import Path

import httpx
import pytest

from pedalpoint.config import get_config
from pedalpoint.server import DEFAULT_SYSTEM, _call_local_llm, _create_draft

RUN = os.getenv("PEDALPOINT_INTEGRATION", "").lower() in {"1", "true", "yes"} and (
    os.getenv("PEDALPOINT_BACKEND") == "mlx"
)


@pytest.mark.skipif(
    not RUN,
    reason="Set PEDALPOINT_INTEGRATION=true and PEDALPOINT_BACKEND=mlx to run",
)
@pytest.mark.asyncio
async def test_live_mlx_writes_parseable_draft(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    get_config.cache_clear()
    cfg = get_config()

    async with httpx.AsyncClient(base_url=cfg.base_url, timeout=cfg.timeout) as client:

        async def generate(prompt: str, system: str) -> tuple[str, int, int]:
            text, usage = await _call_local_llm(client, prompt, system, cfg.model, cfg)
            return (
                text,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

        result = await _create_draft(
            generate,
            task="Write a function `add(a: int, b: int) -> int` that returns a + b.",
            target_path="calc.py",
            context_paths=[],
            system=DEFAULT_SYSTEM,
            repo_root=repo,
            backend=cfg.backend,
            model=cfg.model,
            cfg=cfg,
        )
    get_config.cache_clear()

    draft = Path(result["draft_path"]).read_text()
    ast.parse(draft)
    assert "def add" in draft
    assert "<think>" not in draft
    assert result["completion_tokens"] > 0
