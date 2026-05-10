import os

import httpx
import pytest

from pedalpoint.config import get_config
from pedalpoint.server import _call_local_llm

INTEGRATION = os.getenv("PEDALPOINT_INTEGRATION", "").lower() in {"1", "true", "yes"}


@pytest.mark.skipif(not INTEGRATION, reason="Set PEDALPOINT_INTEGRATION=true to run")
@pytest.mark.asyncio
async def test_live_ollama_returns_nonempty_string() -> None:
    cfg = get_config()
    async with httpx.AsyncClient(base_url=cfg.base_url, timeout=cfg.timeout) as client:
        result = await _call_local_llm(client, "Say hello", None, cfg.model, cfg)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.skipif(not INTEGRATION, reason="Set PEDALPOINT_INTEGRATION=true to run")
@pytest.mark.asyncio
async def test_live_ollama_system_prompt_respected() -> None:
    cfg = get_config()
    async with httpx.AsyncClient(base_url=cfg.base_url, timeout=cfg.timeout) as client:
        result = await _call_local_llm(
            client, "What is 2+2?", "Reply with only the number.", cfg.model, cfg
        )
    assert isinstance(result, str)
    assert len(result) <= 10
