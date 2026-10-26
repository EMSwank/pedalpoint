import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import anthropic
import httpx
from mcp.server.fastmcp import Context, FastMCP

from . import backends, drafting, handoff_log, paths
from .config import Config, get_config

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):  # type: ignore[type-arg]
    cfg = get_config()
    async with httpx.AsyncClient(
        base_url=cfg.base_url,
        timeout=httpx.Timeout(connect=5.0, read=cfg.timeout, write=10.0, pool=5.0),
    ) as client:
        try:
            await client.get("/models", timeout=5.0)
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.warning(
                f"⚠ {backends.label(cfg)} unreachable at %s. Start it with: %s. "
                "local_llm calls will fail until it is running.",
                cfg.base_url,
                backends.start_hint(cfg),
            )
        yield {
            "http": client,
            "cfg": cfg,
            "repo_root": paths.find_repo_root(Path.cwd()),
        }


mcp = FastMCP("pedalpoint", lifespan=lifespan)


async def _call_local_llm(
    client: httpx.AsyncClient,
    prompt: str,
    system: str | None,
    model: str,
    cfg: Config,
) -> tuple[str, dict]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = await client.post(
            "/chat/completions",
            json={"model": model, "messages": messages, "max_tokens": cfg.max_tokens}
            | backends.extra_body(cfg),
        )
        resp.raise_for_status()
        body = resp.json()
        choice = body["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ValueError(
                f"Model output truncated (max_tokens={cfg.max_tokens}) — "
                "raise PEDALPOINT_MAX_TOKENS or split the task"
            )
        return choice["message"]["content"], body.get("usage") or {}
    except httpx.ConnectError:
        raise ValueError(
            f"{backends.label(cfg)} not reachable at {cfg.base_url} — is it running? "
            f"Start: {backends.start_hint(cfg)}"
        ) from None
    except httpx.TimeoutException:
        raise ValueError(
            f"Model timed out after {cfg.timeout}s — increase PEDALPOINT_TIMEOUT"
        ) from None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ValueError(
                f"Model `{model}` not found — run: {backends.pull_hint(cfg, model)}"
            ) from exc
        raise ValueError(
            f"HTTP {exc.response.status_code}: {exc.response.text}"
        ) from exc


Generate = Callable[[str, str], Awaitable[tuple[str, int, int]]]

DEFAULT_SYSTEM = (
    "You are a code generator. Follow the provided patterns exactly. "
    "Output only code. No explanation."
)


def _server_version() -> str:
    try:
        return version("pedalpoint")
    except PackageNotFoundError:  # pragma: no cover - only when run from source
        return "unknown"


def _read_context(spec: str, root: Path) -> tuple[str, str]:
    raw, first, last = paths.parse_context_spec(spec)
    text = paths.resolve_in_repo(raw, root).read_text()
    if first is None:
        return raw, text
    lines = text.splitlines()[first - 1 : last]
    return f"{raw} lines {first}-{last}", "\n".join(lines)


async def _create_draft(
    generate: Generate,
    *,
    task: str,
    target_path: str,
    context_paths: list[str],
    system: str,
    repo_root: Path | None,
    backend: str,
    model: str,
    cfg: Config,
) -> dict:
    """Generate code for `target_path` and write it to `<target_path>.draft`."""
    if repo_root is None:
        raise ValueError("Not in a git repository — local_llm needs a project repo")
    target = paths.resolve_in_repo(target_path, repo_root)
    if target == repo_root.resolve() or target.is_dir():
        raise ValueError(
            f"Target {target_path!r} must be a file inside the project repo"
        )
    context = [_read_context(spec, repo_root) for spec in context_paths]
    existing = target.read_text() if target.exists() else None
    if existing is not None:
        n = len(existing.splitlines())
        if n > drafting.MAX_EDIT_LINES:
            raise ValueError(
                f"Target has {n} lines (> {drafting.MAX_EDIT_LINES}) — too large "
                "for local regeneration; edit directly"
            )
    target_rel = str(target.relative_to(repo_root.resolve()))
    prompt = drafting.build_prompt(task, context, target_rel, existing)
    n_tokens = drafting.estimate_tokens(prompt)
    if n_tokens > cfg.context_limit:
        raise ValueError(
            f"Context too large: ~{n_tokens} tokens > limit {cfg.context_limit} "
            "— escalate to Agent"
        )

    started = time.monotonic()
    text, prompt_tokens, completion_tokens = await generate(prompt, system)
    seconds = round(time.monotonic() - started, 1)
    code = drafting.strip_output(text)
    if not code:
        raise ValueError("Model returned empty output")

    draft = paths.draft_path_for(target)
    draft.parent.mkdir(parents=True, exist_ok=True)
    paths.write_draft(draft, code)
    lines_changed, changed_tokens = drafting.change_size(existing, code)

    result = {
        "handoff_id": uuid.uuid4().hex[:12],
        "draft_path": str(draft),
        "lines": len(code.splitlines()),
        "lines_changed": lines_changed,
        "changed_tokens": changed_tokens,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "seconds": seconds,
        "model": model,
        "backend": backend,
        "server_version": _server_version(),
    }
    handoff_log.append(
        {
            "kind": "call",
            "ts": datetime.now(UTC).isoformat(),
            "repo": str(repo_root),
            "target": target_rel,
            **{k: v for k, v in result.items() if k != "server_version"},
        }
    )
    return result


async def _call_claude_api(
    prompt: str, system: str, cfg: Config
) -> tuple[str, int, int]:
    if not cfg.api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not set. Add it to your environment: "
            "export ANTHROPIC_API_KEY=sk-ant-..."
        )
    client = anthropic.AsyncAnthropic(api_key=cfg.api_key)
    try:
        message = await client.messages.create(
            model=cfg.api_model,
            max_tokens=16384,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return (
            message.content[0].text,
            message.usage.input_tokens,
            message.usage.output_tokens,
        )
    except anthropic.APIStatusError as exc:
        raise ValueError(f"HTTP {exc.status_code}: {exc}") from exc
    except anthropic.APIConnectionError:
        raise ValueError(
            "Anthropic API not reachable — check network connection"
        ) from None


@mcp.tool()
async def claude_api(
    ctx: Context,
    task: str,
    target_path: str,
    context_paths: list[str] | None = None,
    system: str = "",
) -> str:
    """Draft `target_path` with the Claude API. Use when circuit is api_fallback.

    Same contract as `local_llm`: writes `<target_path>.draft`, returns JSON.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    cfg: Config = lifespan_ctx["cfg"]

    async def generate(prompt: str, sys_prompt: str) -> tuple[str, int, int]:
        return await _call_claude_api(prompt, sys_prompt, cfg)

    result = await _create_draft(
        generate,
        task=task,
        target_path=target_path,
        context_paths=context_paths or [],
        system=system or DEFAULT_SYSTEM,
        repo_root=lifespan_ctx.get("repo_root"),
        backend="claude_api",
        model=cfg.api_model,
        cfg=cfg,
    )
    return json.dumps(result)


@mcp.tool()
async def record_outcome(
    ctx: Context, handoff_id: str, score: int, note: str = ""
) -> str:
    """Record what Claude had to do with a draft, 1-7 (7 = accepted as-is)."""
    if not 1 <= score <= 7:
        raise ValueError("score must be 1-7")
    handoff_log.append(
        {
            "kind": "outcome",
            "handoff_id": handoff_id,
            "ts": datetime.now(UTC).isoformat(),
            "score": score,
            "note": note,
        }
    )
    return "recorded"


@mcp.tool()
async def local_llm_status(ctx: Context) -> str:
    """Report backend, model, reachability, pinned repo and server version."""
    lifespan_ctx = ctx.request_context.lifespan_context
    client: httpx.AsyncClient = lifespan_ctx["http"]
    cfg: Config = lifespan_ctx["cfg"]
    try:
        resp = await client.get("/models", timeout=5.0)
        reachable = resp.status_code == 200
    except httpx.HTTPError:
        reachable = False
    repo_root = lifespan_ctx.get("repo_root")
    return json.dumps(
        {
            "backend": cfg.backend,
            "model": cfg.model,
            "base_url": cfg.base_url,
            "reachable": reachable,
            "repo_root": str(repo_root) if repo_root else None,
            "server_version": _server_version(),
        }
    )


@mcp.tool()
async def local_llm(
    ctx: Context,
    task: str,
    target_path: str,
    context_paths: list[str] | None = None,
    system: str | None = None,
    model: str | None = None,
) -> str:
    """Draft `target_path` with the local model; writes `<target_path>.draft`.

    Pass context as file paths ("path" or "path:START-END"), not pasted code.
    Returns a JSON summary including `handoff_id` for `record_outcome`.
    """
    lifespan_ctx = ctx.request_context.lifespan_context
    client: httpx.AsyncClient = lifespan_ctx["http"]
    cfg: Config = lifespan_ctx["cfg"]
    chosen = model or cfg.model

    async def generate(prompt: str, sys_prompt: str) -> tuple[str, int, int]:
        text, usage = await _call_local_llm(client, prompt, sys_prompt, chosen, cfg)
        return (
            text,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )

    result = await _create_draft(
        generate,
        task=task,
        target_path=target_path,
        context_paths=context_paths or [],
        system=system or DEFAULT_SYSTEM,
        repo_root=lifespan_ctx.get("repo_root"),
        backend=cfg.backend,
        model=chosen,
        cfg=cfg,
    )
    return json.dumps(result)


def main() -> None:
    mcp.run()
