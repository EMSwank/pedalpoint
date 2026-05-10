import json

import httpx
import pytest
import respx

from pedalpoint.config import Config
from pedalpoint.server import _call_local_llm

TEST_CFG = Config(
    base_url="http://localhost:11434/v1",
    model="gemma4:e4b",
    mode="hybrid",
    timeout=120.0,
    initial_fallback_minutes=60,
    context_limit=16000,
)

MOCK_RESPONSE = {
    "choices": [{"message": {"content": "def foo(): pass"}}]
}


@respx.mock
@pytest.mark.asyncio
async def test_basic_prompt_returns_content() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=MOCK_RESPONSE)
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        result = await _call_local_llm(
            client, "write foo", None, "gemma4:e4b", TEST_CFG
        )
    assert result == "def foo(): pass"


@respx.mock
@pytest.mark.asyncio
async def test_system_prompt_included_in_messages() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=MOCK_RESPONSE)
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        await _call_local_llm(client, "write foo", "be terse", "gemma4:e4b", TEST_CFG)
    payload = json.loads(route.calls[0].request.content)
    messages = payload["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "be terse"
    assert messages[1]["role"] == "user"


@respx.mock
@pytest.mark.asyncio
async def test_no_system_prompt_omits_system_message() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=MOCK_RESPONSE)
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        await _call_local_llm(client, "write foo", None, "gemma4:e4b", TEST_CFG)
    payload = json.loads(route.calls[0].request.content)
    roles = [m["role"] for m in payload["messages"]]
    assert "system" not in roles


@respx.mock
@pytest.mark.asyncio
async def test_model_sent_in_payload() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=MOCK_RESPONSE)
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        await _call_local_llm(client, "write foo", None, "llama3", TEST_CFG)
    payload = json.loads(route.calls[0].request.content)
    assert payload["model"] == "llama3"


@respx.mock
@pytest.mark.asyncio
async def test_connect_error_raises_clear_message() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("refused")
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        with pytest.raises(ValueError, match="Ollama not reachable"):
            await _call_local_llm(client, "prompt", None, "gemma4:e4b", TEST_CFG)


@respx.mock
@pytest.mark.asyncio
async def test_timeout_raises_clear_message() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        with pytest.raises(ValueError, match="timed out after"):
            await _call_local_llm(client, "prompt", None, "gemma4:e4b", TEST_CFG)


@respx.mock
@pytest.mark.asyncio
async def test_404_raises_model_not_found_message() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(404, text="model not found")
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        with pytest.raises(ValueError, match="ollama pull"):
            await _call_local_llm(client, "prompt", None, "gemma4:e4b", TEST_CFG)


@respx.mock
@pytest.mark.asyncio
async def test_500_forwards_status_and_body() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="internal error")
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        with pytest.raises(ValueError, match="HTTP 500"):
            await _call_local_llm(client, "prompt", None, "gemma4:e4b", TEST_CFG)
