import logging
from contextlib import asynccontextmanager

import anthropic
import httpx
from mcp.server.fastmcp import Context, FastMCP

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
                "⚠ Ollama unreachable at %s. Run `ollama serve` or open "
                "Ollama.app. local_llm calls will fail until Ollama is running.",
                cfg.base_url,
            )
        yield {"http": client, "cfg": cfg}


mcp = FastMCP("pedalpoint", lifespan=lifespan)


async def _call_local_llm(
    client: httpx.AsyncClient,
    prompt: str,
    system: str | None,
    model: str,
    cfg: Config,
) -> str:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = await client.post(
            "/chat/completions",
            json={"model": model, "messages": messages},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.ConnectError:
        raise ValueError(
            f"Ollama not reachable at {cfg.base_url} — is it running?"
        ) from None
    except httpx.TimeoutException:
        raise ValueError(
            f"Model timed out after {cfg.timeout}s — increase PEDALPOINT_TIMEOUT"
        ) from None
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ValueError(
                f"Model `{model}` not found — run: ollama pull {model}"
            ) from exc
        raise ValueError(
            f"HTTP {exc.response.status_code}: {exc.response.text}"
        ) from exc


async def _call_claude_api(prompt: str, system: str, cfg: Config) -> str:
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
        return message.content[0].text
    except anthropic.APIStatusError as exc:
        raise ValueError(f"HTTP {exc.status_code}: {exc}") from exc
    except anthropic.APIConnectionError:
        raise ValueError(
            "Anthropic API not reachable — check network connection"
        ) from None


@mcp.tool()
async def claude_api(
    ctx: Context,
    prompt: str,
    system: str = "",
) -> str:
    """Call Claude API directly. Use when circuit is api_fallback."""
    cfg: Config = ctx.request_context.lifespan_context["cfg"]
    return await _call_claude_api(
        prompt,
        system or "You are a code generator. Output only code. No explanation.",
        cfg,
    )


@mcp.tool()
async def local_llm(
    ctx: Context,
    prompt: str,
    system: str | None = None,
    model: str | None = None,
) -> str:
    client: httpx.AsyncClient = ctx.request_context.lifespan_context["http"]
    cfg: Config = ctx.request_context.lifespan_context["cfg"]
    return await _call_local_llm(client, prompt, system, model or cfg.model, cfg)


def main() -> None:
    mcp.run()
