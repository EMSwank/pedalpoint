import dataclasses
import json
from pathlib import Path
from typing import get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from mcp.server.fastmcp import Context

from pedalpoint.config import Config, get_config
from pedalpoint.server import (
    _call_claude_api,
    _call_local_llm,
    _create_draft,
    lifespan,
    local_llm,
)


def test_local_llm_ctx_typed_as_context() -> None:
    hints = get_type_hints(local_llm)
    assert hints.get("ctx") is Context


TEST_CFG = Config(
    base_url="http://localhost:11434/v1",
    model="gemma4:12b",
    backend="ollama",
    mode="hybrid",
    timeout=120.0,
    initial_fallback_minutes=60,
    context_limit=16000,
    api_model="claude-sonnet-4-6",
    api_key=None,
)

TEST_CFG_WITH_KEY = Config(
    base_url="http://localhost:11434/v1",
    model="gemma4:12b",
    backend="ollama",
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
        text, usage = await _call_local_llm(
            client, "write foo", None, "gemma4:12b", TEST_CFG
        )
    assert text == "def foo(): pass"
    assert usage == {}


@respx.mock
@pytest.mark.asyncio
async def test_system_prompt_included_in_messages() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=MOCK_RESPONSE)
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        await _call_local_llm(client, "write foo", "be terse", "gemma4:12b", TEST_CFG)
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
        await _call_local_llm(client, "write foo", None, "gemma4:12b", TEST_CFG)
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
            await _call_local_llm(client, "prompt", None, "gemma4:12b", TEST_CFG)


@respx.mock
@pytest.mark.asyncio
async def test_timeout_raises_clear_message() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        side_effect=httpx.TimeoutException("timed out")
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        with pytest.raises(ValueError, match="timed out after"):
            await _call_local_llm(client, "prompt", None, "gemma4:12b", TEST_CFG)


@respx.mock
@pytest.mark.asyncio
async def test_404_raises_model_not_found_message() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(404, text="model not found")
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        with pytest.raises(ValueError, match="ollama pull"):
            await _call_local_llm(client, "prompt", None, "gemma4:12b", TEST_CFG)


@respx.mock
@pytest.mark.asyncio
async def test_500_forwards_status_and_body() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="internal error")
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        with pytest.raises(ValueError, match="HTTP 500"):
            await _call_local_llm(client, "prompt", None, "gemma4:12b", TEST_CFG)


@pytest.mark.asyncio
async def test_claude_api_no_key_raises_value_error() -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not set"):
        await _call_claude_api("write foo", "be terse", TEST_CFG)


@pytest.mark.asyncio
async def test_claude_api_success_returns_text() -> None:
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="def foo(): pass")]
    mock_msg.usage.input_tokens = 3
    mock_msg.usage.output_tokens = 4
    mock_client = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_msg)
    with patch("pedalpoint.server.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await _call_claude_api("write foo", "be terse", TEST_CFG_WITH_KEY)
    assert result == ("def foo(): pass", 3, 4)


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


# ── lifespan ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_lifespan_yields_http_and_cfg_when_ollama_reachable(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_config.cache_clear()
    respx.get("http://localhost:11434/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    async with lifespan(None) as ctx:
        assert "http" in ctx
        assert "cfg" in ctx
    get_config.cache_clear()


@pytest.mark.asyncio
@respx.mock
async def test_lifespan_warns_but_still_yields_when_ollama_unreachable(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_config.cache_clear()
    respx.get("http://localhost:11434/v1/models").mock(
        side_effect=httpx.ConnectError("refused")
    )
    with patch("pedalpoint.server.logger") as mock_logger:
        async with lifespan(None) as ctx:
            assert "http" in ctx
            mock_logger.warning.assert_called_once()
            assert "Ollama unreachable" in mock_logger.warning.call_args[0][0]
    get_config.cache_clear()


# ── backend-aware _call_local_llm ───────────────────────────────────────────

MLX_CFG = dataclasses.replace(
    TEST_CFG,
    base_url="http://localhost:8080/v1",
    model="mlx-community/gemma-4-e4b-it-4bit",
    backend="mlx",
)
MLX_URL = "http://localhost:8080/v1/chat/completions"


@respx.mock
@pytest.mark.asyncio
async def test_call_local_llm_returns_usage() -> None:
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                **MOCK_RESPONSE,
                "usage": {"prompt_tokens": 12, "completion_tokens": 34},
            },
        )
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        _, usage = await _call_local_llm(client, "p", None, "gemma4:12b", TEST_CFG)
    assert usage == {"prompt_tokens": 12, "completion_tokens": 34}


@respx.mock
@pytest.mark.asyncio
async def test_call_local_llm_sends_mlx_thinking_off() -> None:
    route = respx.post(MLX_URL).mock(
        return_value=httpx.Response(200, json=MOCK_RESPONSE)
    )
    async with httpx.AsyncClient(base_url=MLX_CFG.base_url) as client:
        await _call_local_llm(client, "p", None, MLX_CFG.model, MLX_CFG)
    payload = json.loads(route.calls[0].request.content)
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}


@respx.mock
@pytest.mark.asyncio
async def test_call_local_llm_sends_ollama_reasoning_none() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=MOCK_RESPONSE)
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        await _call_local_llm(client, "p", None, "gemma4:12b", TEST_CFG)
    payload = json.loads(route.calls[0].request.content)
    assert payload["reasoning_effort"] == "none"


@respx.mock
@pytest.mark.asyncio
async def test_call_local_llm_errors_use_backend_hints() -> None:
    respx.post(MLX_URL).mock(side_effect=httpx.ConnectError("refused"))
    async with httpx.AsyncClient(base_url=MLX_CFG.base_url) as client:
        with pytest.raises(ValueError, match="MLX not reachable") as exc:
            await _call_local_llm(client, "p", None, MLX_CFG.model, MLX_CFG)
    assert "mlx_lm.server" in str(exc.value)


@respx.mock
@pytest.mark.asyncio
async def test_call_local_llm_404_mlx_suggests_hf_download() -> None:
    respx.post(MLX_URL).mock(return_value=httpx.Response(404, text="nope"))
    async with httpx.AsyncClient(base_url=MLX_CFG.base_url) as client:
        with pytest.raises(ValueError, match="hf download"):
            await _call_local_llm(client, "p", None, MLX_CFG.model, MLX_CFG)


# ── _create_draft ───────────────────────────────────────────────────────────


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "src").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return root.resolve()


def _fake_generate(output: str, prompts: list | None = None):
    async def generate(prompt: str, system: str) -> tuple[str, int, int]:
        if prompts is not None:
            prompts.append(prompt)
        return output, 11, 22

    return generate


async def _draft(repo: Path, output: str, **kwargs) -> dict:
    params = {
        "task": "do it",
        "target_path": "src/new.py",
        "context_paths": [],
        "system": "sys",
        "repo_root": repo,
        "backend": "ollama",
        "model": "gemma4:12b",
        "cfg": TEST_CFG,
    }
    params.update(kwargs)
    return await _create_draft(_fake_generate(output), **params)


def _log_records(repo: Path) -> list[dict]:
    path = repo.parent / "home" / ".pedalpoint" / "handoffs.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.asyncio
async def test_create_draft_new_file(repo: Path) -> None:
    result = await _draft(repo, "```python\nx = 1\ny = 2\n```")
    draft = repo / "src" / "new.py.draft"
    assert draft.read_text() == "x = 1\ny = 2\n"
    assert not (repo / "src" / "new.py").exists()
    assert result["draft_path"] == str(draft)
    assert result["lines"] == 2 and result["lines_changed"] == 2
    assert result["prompt_tokens"] == 11 and result["completion_tokens"] == 22
    assert result["backend"] == "ollama" and result["model"] == "gemma4:12b"
    assert result["server_version"]
    records = _log_records(repo)
    assert len(records) == 1
    assert records[0]["kind"] == "call"
    assert records[0]["handoff_id"] == result["handoff_id"]
    assert records[0]["repo"] == str(repo)
    assert records[0]["changed_tokens"] == result["changed_tokens"]


@pytest.mark.asyncio
async def test_create_draft_creates_parent_dirs(repo: Path) -> None:
    await _draft(repo, "x = 1\n", target_path="src/pkg/new/mod.py")
    assert (repo / "src" / "pkg" / "new" / "mod.py.draft").read_text() == "x = 1\n"


@pytest.mark.asyncio
async def test_create_draft_edit_existing_counts_changes(repo: Path) -> None:
    original = "".join(f"v{i} = {i}\n" for i in range(50))
    (repo / "src" / "mod.py").write_text(original)
    prompts: list[str] = []
    result = await _create_draft(
        _fake_generate(original + "a = 1\nb = 2\n", prompts),
        task="add a and b",
        target_path="src/mod.py",
        context_paths=[],
        system="sys",
        repo_root=repo,
        backend="ollama",
        model="gemma4:12b",
        cfg=TEST_CFG,
    )
    assert result["lines_changed"] == 2
    assert "## Current contents of src/mod.py" in prompts[0]
    assert (repo / "src" / "mod.py").read_text() == original


@pytest.mark.asyncio
async def test_create_draft_context_slice_in_prompt(repo: Path) -> None:
    (repo / "src" / "a.py").write_text("one\ntwo\nthree\nfour\n")
    prompts: list[str] = []
    await _create_draft(
        _fake_generate("x = 1\n", prompts),
        task="t",
        target_path="src/new.py",
        context_paths=["src/a.py:2-3"],
        system="sys",
        repo_root=repo,
        backend="ollama",
        model="gemma4:12b",
        cfg=TEST_CFG,
    )
    assert "## Context: src/a.py lines 2-3" in prompts[0]
    assert "two\nthree" in prompts[0]
    assert "one" not in prompts[0] and "four" not in prompts[0]


@pytest.mark.asyncio
async def test_create_draft_outside_repo_raises(repo: Path) -> None:
    with pytest.raises(ValueError, match="outside the project repo"):
        await _draft(repo, "x\n", target_path="../evil.py")
    with pytest.raises(ValueError, match="outside the project repo"):
        await _draft(repo, "x\n", context_paths=["/etc/hosts"])


@pytest.mark.asyncio
async def test_create_draft_no_repo_raises(repo: Path) -> None:
    with pytest.raises(ValueError, match="Not in a git repository"):
        await _draft(repo, "x\n", repo_root=None)


@pytest.mark.asyncio
async def test_create_draft_too_many_lines_raises(repo: Path) -> None:
    (repo / "src" / "big.py").write_text("x = 1\n" * 301)
    with pytest.raises(ValueError, match=r"301 lines \(> 300\)"):
        await _draft(repo, "x\n", target_path="src/big.py")


@pytest.mark.asyncio
async def test_create_draft_context_too_large_raises(repo: Path) -> None:
    small = dataclasses.replace(TEST_CFG, context_limit=5)
    with pytest.raises(ValueError, match="Context too large"):
        await _draft(repo, "x\n", cfg=small)


@pytest.mark.asyncio
async def test_create_draft_empty_output_raises_and_writes_nothing(
    repo: Path,
) -> None:
    with pytest.raises(ValueError, match="Model returned empty output"):
        await _draft(repo, "<think>hm</think>")
    assert not (repo / "src" / "new.py.draft").exists()
    assert _log_records(repo) == []


@respx.mock
@pytest.mark.asyncio
async def test_local_llm_tool_returns_json(repo: Path) -> None:
    from pedalpoint.server import local_llm

    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                **MOCK_RESPONSE,
                "usage": {"prompt_tokens": 5, "completion_tokens": 7},
            },
        )
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as http_client:
        ctx = _make_ctx(TEST_CFG, http_client=http_client)
        ctx.request_context.lifespan_context["repo_root"] = repo
        raw = await local_llm(ctx, "write foo", "src/foo.py")
    result = json.loads(raw)
    assert set(result) == {
        "handoff_id",
        "draft_path",
        "lines",
        "lines_changed",
        "changed_tokens",
        "prompt_tokens",
        "completion_tokens",
        "seconds",
        "model",
        "backend",
        "server_version",
    }
    assert result["completion_tokens"] == 7
    assert (repo / "src" / "foo.py.draft").read_text() == "def foo(): pass\n"


@pytest.mark.asyncio
@respx.mock
async def test_lifespan_pins_repo_root(monkeypatch, repo: Path) -> None:
    monkeypatch.chdir(repo / "src")
    get_config.cache_clear()
    respx.get("http://localhost:11434/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    async with lifespan(None) as ctx:
        assert ctx["repo_root"] == repo
    get_config.cache_clear()


# ── claude_api drafts, record_outcome, local_llm_status ─────────────────────


@pytest.mark.asyncio
async def test_claude_api_writes_draft(repo: Path) -> None:
    from pedalpoint.server import claude_api

    ctx = _make_ctx(TEST_CFG_WITH_KEY)
    ctx.request_context.lifespan_context["repo_root"] = repo
    with patch(
        "pedalpoint.server._call_claude_api",
        new=AsyncMock(return_value=("x = 1\n", 9, 8)),
    ) as mock_fn:
        result = json.loads(await claude_api(ctx, "write x", "src/x.py"))
    assert result["backend"] == "claude_api"
    assert result["model"] == "claude-sonnet-4-6"
    assert result["completion_tokens"] == 8
    assert (repo / "src" / "x.py.draft").read_text() == "x = 1\n"
    assert "code generator" in mock_fn.call_args.args[1]


@pytest.mark.asyncio
async def test_record_outcome_appends(repo: Path) -> None:
    from pedalpoint.server import record_outcome

    ctx = _make_ctx(TEST_CFG)
    assert await record_outcome(ctx, "abc123", 6, "fixed import") == "recorded"
    records = _log_records(repo)
    assert records[-1]["kind"] == "outcome"
    assert records[-1]["handoff_id"] == "abc123"
    assert records[-1]["score"] == 6
    assert records[-1]["note"] == "fixed import"
    assert "ts" in records[-1]


@pytest.mark.parametrize("score", [0, 8])
@pytest.mark.asyncio
async def test_record_outcome_rejects_out_of_range(repo: Path, score: int) -> None:
    from pedalpoint.server import record_outcome

    with pytest.raises(ValueError, match="score must be 1-7"):
        await record_outcome(_make_ctx(TEST_CFG), "abc", score)
    assert _log_records(repo) == []


@respx.mock
@pytest.mark.asyncio
async def test_local_llm_status_reachable(repo: Path) -> None:
    from pedalpoint.server import local_llm_status

    respx.get("http://localhost:11434/v1/models").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        ctx = _make_ctx(TEST_CFG, http_client=client)
        ctx.request_context.lifespan_context["repo_root"] = repo
        status = json.loads(await local_llm_status(ctx))
    assert status["reachable"] is True
    assert status["backend"] == "ollama"
    assert status["model"] == "gemma4:12b"
    assert status["base_url"] == "http://localhost:11434/v1"
    assert status["repo_root"] == str(repo)
    assert status["server_version"]


@respx.mock
@pytest.mark.asyncio
async def test_local_llm_status_unreachable() -> None:
    from pedalpoint.server import local_llm_status

    respx.get("http://localhost:11434/v1/models").mock(
        side_effect=httpx.ConnectError("refused")
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        ctx = _make_ctx(TEST_CFG, http_client=client)
        status = json.loads(await local_llm_status(ctx))
    assert status["reachable"] is False
    assert status["repo_root"] is None


# ── final-review fixes ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_draft_symlinked_draft_does_not_write_through(
    repo: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("ORIGINAL\n")
    (repo / "src" / "util.py.draft").symlink_to(outside)
    await _draft(repo, "PWNED = 1\n", target_path="src/util.py")
    assert outside.read_text() == "ORIGINAL\n"
    draft = repo / "src" / "util.py.draft"
    assert not draft.is_symlink()
    assert draft.read_text() == "PWNED = 1\n"


@pytest.mark.parametrize("target", [".", "", "src"])
@pytest.mark.asyncio
async def test_create_draft_rejects_directory_target(repo: Path, target: str) -> None:
    with pytest.raises(ValueError, match="must be a file"):
        await _draft(repo, "x = 1\n", target_path=target)
    assert not (repo.parent / "repo.draft").exists()
