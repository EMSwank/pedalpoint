# pedalpoint — Developer Guide

## Project Overview

MCP server + companion superpowers skill. Two deliverables:
1. `pedalpoint-server` — Python binary (FastMCP, httpx)
2. `skills/route-tasks/SKILL.md` — Markdown skill for Claude Code

## Key Design Decisions

- **Draft-writing server, smart skill:** All routing logic lives in the skill. The server reads context files and writes the model's output to `<target>.draft` — only `.draft` paths, only inside the git repo pinned at startup (toplevel of its cwd). Claude reviews the draft and promotes it with `mv`, never re-typing code (that re-typing was why handoffs cost more than they saved). Server never touches `~/.pedalpoint/state.json`.
- **MLX autostart:** `autostart.py`. On a `local_llm` call with a local MLX URL, the server touches `~/.pedalpoint/mlx.last_used` and, if MLX is down, spawns a detached `pedalpoint mlx-supervise` (one per machine, guarded by `flock` on `mlx.supervisor.lock`; sessions serialize on `mlx.start.lock`). The supervisor owns `mlx_lm.server` and stops it after `PEDALPOINT_IDLE_MINUTES` (default 20) without a touch from any session. A hand-started server is never stopped.
- **Backends:** `PEDALPOINT_BACKEND=mlx|ollama`. Both speak OpenAI `/v1/chat/completions`; backend only changes defaults, hint text, and the "thinking off" request field (`backends.py`).
- **Three-tier routing (junior/senior model):** Local LLM = junior dev, Claude = senior dev. Mechanical and structural tasks get a local `.draft` that Claude reviews inline (no review subagent) and scores 1–7 via `record_outcome`. Judgment tasks (architecture, debugging, security) go to Agent only. Changes under ~30 lines skip the handoff.
- **No streaming:** `local_llm` waits for the full completion. Simpler, sufficient for code gen.
- **Savings metrics:** `pedalpoint stats` joins `~/.pedalpoint/handoffs.jsonl` with Claude Code transcripts (`~/.claude/projects/*/*.jsonl`, undocumented format — parse defensively) for real per-handoff Claude cost.
- **Circuit breaker in skill:** Claude reads/writes state.json via Write tool. Python `circuit_breaker.py` module contains the pure functions that document and validate this logic.
- **Context Courier:** Skill MUST grep codebase before sending any task to local LLM. Empty grep result = escalate to Agent.

## Branch Strategy

- `main` — always stable, PR only, squash merge
- `feat/<name>` — new functionality
- `fix/<name>` — bug fixes
- `chore/<name>` — tooling, config, deps
- `test/<name>` — test-only changes
- `docs/<name>` — documentation

Branch on everything, including README and CLAUDE.md changes.

## TDD Workflow

1. Write failing test
2. Run to confirm failure
3. Implement minimal code
4. Run to confirm pass
5. Commit

Coverage requirements: circuit_breaker.py = 100%, error_classifier.py = 100%, paths.py / drafting.py / stats.py / autostart.py = 100%, server.py ≥ 90%

## Running Tests

```sh
# Unit tests (fast, no Ollama needed)
pytest tests/unit/ -v --cov=pedalpoint --cov-report=term-missing

# Integration tests — Ollama (gemma4:12b pulled; CI pins gemma4:e4b via PEDALPOINT_MODEL)
PEDALPOINT_INTEGRATION=true PEDALPOINT_BACKEND=ollama pytest tests/integration/test_ollama.py -v

# Integration tests — MLX (run: mlx_lm.server --model mlx-community/gemma-4-e4b-it-4bit)
PEDALPOINT_INTEGRATION=true PEDALPOINT_BACKEND=mlx pytest tests/integration/test_mlx.py -v

# All unit tests with coverage check
pytest tests/unit/ --cov=pedalpoint --cov-fail-under=90
```

## File Responsibilities

| File | Responsibility |
|---|---|
| `src/pedalpoint/config.py` | Load env vars into frozen Config dataclass |
| `src/pedalpoint/error_classifier.py` | Regex classify error strings → error type |
| `src/pedalpoint/circuit_breaker.py` | Pure fns for state transitions, expiry, backoff |
| `src/pedalpoint/backends.py` | Per-backend labels, start/pull hints, thinking-off request fields |
| `src/pedalpoint/paths.py` | Repo root discovery, path-in-repo enforcement, context specs, `.draft` paths |
| `src/pedalpoint/drafting.py` | Prompt assembly, output cleanup (`<think>`, fences), change sizing |
| `src/pedalpoint/autostart.py` | Start `mlx_lm.server` on demand, shared idle clock, supervisor loop |
| `src/pedalpoint/handoff_log.py` | Append/read `~/.pedalpoint/handoffs.jsonl` |
| `src/pedalpoint/server.py` | FastMCP app, lifespan, `_create_draft`, tools `local_llm` / `claude_api` / `record_outcome` / `local_llm_status` |
| `src/pedalpoint/transcripts.py` | Per-handoff Claude token costs from Claude Code transcripts |
| `src/pedalpoint/stats.py` | Net-savings math and the `pedalpoint stats` table |
| `src/pedalpoint/doctor.py` / `cli.py` | `pedalpoint doctor`, `pedalpoint stats`, `pedalpoint mlx-supervise` (internal), `--version` |
| `skills/route-tasks/SKILL.md` | Claude instructions: routing, Context Courier, circuit breaker |
| `install.sh` | Install pkg, install mlx-lm + download model (mlx) or pull model (ollama), register MCP config, fetch skill pinned to the release tag |

## State File Format

`~/.pedalpoint/state.json`:
```json
{
  "circuit": "open",
  "reason": "402_quota",
  "opened_at": "2026-05-08T15:30:00+00:00",
  "expires": "2026-05-08T16:30:00+00:00",
  "failure_count": 1,
  "fallback_duration_minutes": 60,
  "tasks_rerouted": 3
}
```

CLOSED state: `{"circuit": "closed"}` or file absent.

`~/.pedalpoint/handoffs.jsonl` (written by the server, one JSON object per line):
- `{"kind": "call", "handoff_id", "ts", "repo", "backend", "model", "target", "draft_path", "lines", "lines_changed", "changed_tokens", "prompt_tokens", "completion_tokens", "seconds"}`
- `{"kind": "outcome", "handoff_id", "ts", "score", "note"}`

API_FALLBACK state: same schema as OPEN but `"circuit": "api_fallback"`. Judgment/structural tasks route to `claude_api`; mechanical tasks still use local_llm.

## Common Gotchas

- `get_config()` uses `lru_cache`. Tests must call `get_config.cache_clear()` before and after monkeypatching env vars.
- `_create_draft` is the testable core shared by `local_llm` and `claude_api`; it takes a `generate(prompt, system) -> (text, prompt_tokens, completion_tokens)` callable.
- Backend inference: `PEDALPOINT_BACKEND` wins; else a set `PEDALPOINT_BASE_URL` containing `:11434` → ollama, other URL → mlx; else `_platform_default_backend()` (mlx on macOS arm64). `tests/conftest.py` pins the platform to Linux so defaults are host-independent — tests needing mlx defaults monkeypatch `pedalpoint.config._platform_default_backend`.
- `mlx_lm.server`'s `/v1/models` lists every model in the local HF cache, so doctor's "model available" means downloaded. When MLX is down and autostart applies, doctor checks the HF cache directory instead (`HF_HUB_CACHE` → `HF_HOME/hub` → `~/.cache/huggingface/hub`).
- The supervisor is launched as `sys.executable -m pedalpoint.cli mlx-supervise`, so `cli.py` keeps its `if __name__ == "__main__"` guard. Its tests inject `popen`/`sleep`/`now`; never let a unit test start a real model.
- Backend resolution order: `PEDALPOINT_BACKEND` → `PEDALPOINT_BASE_URL` inference → `~/.pedalpoint/backend` (written by install.sh) → platform default. `tests/conftest.py` points `HOME` at a temp dir so the real file never leaks into tests.
- Always send `max_tokens` (`PEDALPOINT_MAX_TOKENS`, default 8192): `mlx_lm.server` defaults to 512 and silently truncates; `finish_reason == "length"` raises instead of writing a draft.
- 402 errors trigger permanent fallback. 429 errors trigger retry-with-backoff only. Do not conflate them.
- The companion skill has no Python backing. Skill tests are manual scenarios in `tests/skill/scenarios/`.
- `ANTHROPIC_API_KEY` is optional at startup. If absent, `_call_claude_api` raises `ValueError("ANTHROPIC_API_KEY not set...")`. FastMCP stringifies it; the skill's error dispatch table matches on that text and writes OPEN state.
- `PEDALPOINT_API_MODEL` defaults to `"claude-sonnet-4-6"`. Update this env var when a newer Sonnet is released rather than editing code.
