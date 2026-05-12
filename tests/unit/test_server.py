import json
from typing import get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from mcp.server.fastmcp import Context

from pedalpoint.config import Config
from pedalpoint.server import _call_claude_api, _call_local_llm, local_llm


def test_local_llm_ctx_typed_as_context() -> None:
    hints = get_type_hints(local_llm)
    assert hints.get("ctx") is Context


TEST_CFG = Config(
    base_url="http://localhost:11434/v1",
    model="gemma4:e4b",
    mode="hybrid",
    timeout=120.0,
    initial_fallback_minutes=60,
    context_limit=16000,
    api_model="claude-sonnet-4-6",
    api_key=None,
)

TEST_CFG_WITH_KEY = Config(
    base_url="http://localhost:11434/v1",
    model="gemma4:e4b",
    mode="hybrid",
    timeout=120.0,
    initial_fallback_minutes=60,
    context_limit=16000,
    api_model="claude-sonnet-4-6",
    api_key="sk-ant-test",
)

MOCK_RESPONSE = {"choices": [{"message": {"content": "def foo(): pass"}}]}


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


@pytest.mark.asyncio
async def test_claude_api_no_key_returns_error_string() -> None:
    result = await _call_claude_api("write foo", "be terse", TEST_CFG)
    assert result == "ERROR: ANTHROPIC_API_KEY not set — claude_api unavailable."


@pytest.mark.asyncio
async def test_claude_api_success_returns_text() -> None:
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="def foo(): pass")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)
    with patch("pedalpoint.server.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await _call_claude_api("write foo", "be terse", TEST_CFG_WITH_KEY)
    assert result == "def foo(): pass"


@pytest.mark.asyncio
async def test_claude_api_passes_model_from_config() -> None:
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="ok")]
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)
    with patch("pedalpoint.server.anthropic.AsyncAnthropic", return_value=mock_client):
        await _call_claude_api("prompt", "system", TEST_CFG_WITH_KEY)
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_claude_api_http_error_raises_valueerror() -> None:
    import anthropic as anthropic_sdk
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=anthropic_sdk.APIStatusError(
            "quota exceeded",
            response=MagicMock(status_code=402),
            body={},
        )
    )
    with patch("pedalpoint.server.anthropic.AsyncAnthropic", return_value=mock_client):
        with pytest.raises(ValueError, match="HTTP 402"):
            await _call_claude_api("prompt", "system", TEST_CFG_WITH_KEY)


@pytest.mark.asyncio
async def test_claude_api_connection_error_raises_valueerror() -> None:
    import anthropic as anthropic_sdk
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(
        side_effect=anthropic_sdk.APIConnectionError(request=MagicMock())
    )
    with patch("pedalpoint.server.anthropic.AsyncAnthropic", return_value=mock_client):
        with pytest.raises(ValueError, match="Anthropic API not reachable"):
            await _call_claude_api("prompt", "system", TEST_CFG_WITH_KEY)


def _make_ctx(cfg: Config, http_client: object = None) -> MagicMock:
    ctx = MagicMock(spec=Context)
    lifespan_ctx: dict = {"cfg": cfg}
    if http_client is not None:
        lifespan_ctx["http"] = http_client
    ctx.request_context.lifespan_context = lifespan_ctx
    return ctx


@pytest.mark.asyncio
async def test_claude_api_tool_delegates_to_call_claude_api() -> None:
    from pedalpoint.server import claude_api

    ctx = _make_ctx(TEST_CFG_WITH_KEY)
    with patch(
        "pedalpoint.server._call_claude_api", new=AsyncMock(return_value="result text")
    ) as mock_fn:
        result = await claude_api(ctx, "hello", "be concise")
    mock_fn.assert_awaited_once_with("hello", "be concise", TEST_CFG_WITH_KEY)
    assert result == "result text"


@pytest.mark.asyncio
async def test_claude_api_tool_uses_default_system_when_empty() -> None:
    from pedalpoint.server import claude_api

    ctx = _make_ctx(TEST_CFG_WITH_KEY)
    with patch(
        "pedalpoint.server._call_claude_api", new=AsyncMock(return_value="ok")
    ) as mock_fn:
        await claude_api(ctx, "hello", "")
    call_args = mock_fn.call_args
    assert "code generator" in call_args.args[1]


@respx.mock
@pytest.mark.asyncio
async def test_local_llm_tool_delegates_to_call_local_llm() -> None:
    from pedalpoint.server import local_llm

    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=MOCK_RESPONSE)
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as http_client:
        ctx = _make_ctx(TEST_CFG, http_client=http_client)
        result = await local_llm(ctx, "write foo", "be terse", "gemma4:e4b")
    assert result == "def foo(): pass"
