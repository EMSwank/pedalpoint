from contextlib import asynccontextmanager

import httpx
from mcp.server.fastmcp import FastMCP

from .config import Config, get_config


@asynccontextmanager
async def lifespan(app):  # type: ignore[type-arg]
    cfg = get_config()
    async with httpx.AsyncClient(
        base_url=cfg.base_url,
        timeout=httpx.Timeout(connect=5.0, read=cfg.timeout, write=10.0, pool=5.0),
    ) as client:
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
        )
    except httpx.TimeoutException:
        raise ValueError(
            f"Model timed out after {cfg.timeout}s — increase PEDALPOINT_TIMEOUT"
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ValueError(
                f"Model `{model}` not found — run: ollama pull {model}"
            )
        raise ValueError(f"HTTP {exc.response.status_code}: {exc.response.text}")


@mcp.tool()
async def local_llm(
    ctx,  # type: ignore[type-arg]
    prompt: str,
    system: str | None = None,
    model: str | None = None,
) -> str:
    client: httpx.AsyncClient = ctx.request_context.lifespan_context["http"]
    cfg: Config = ctx.request_context.lifespan_context["cfg"]
    return await _call_local_llm(client, prompt, system, model or cfg.model, cfg)


def main() -> None:
    mcp.run()
