# pedalpoint — Developer Guide

## Project Overview

MCP server + companion superpowers skill. Two deliverables:
1. `pedalpoint-server` — Python binary (FastMCP, httpx)
2. `skills/route-tasks.md` — Markdown skill for Claude Code

## Key Design Decisions

- **Thin server, smart skill:** Server is a pure HTTP proxy. All routing logic lives in the skill. Server never touches `~/.pedalpoint/state.json`.
- **No streaming:** `local_llm` returns full string. Simpler, sufficient for code gen.
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

Coverage requirements: circuit_breaker.py = 100%, error_classifier.py = 100%, server.py ≥ 90%

## Running Tests

```sh
# Unit tests (fast, no Ollama needed)
pytest tests/unit/ -v --cov=pedalpoint --cov-report=term-missing

# Integration tests (requires Ollama running with gemma4:e4b pulled)
PEDALPOINT_INTEGRATION=true pytest tests/integration/ -v

# All unit tests with coverage check
pytest tests/unit/ --cov=pedalpoint --cov-fail-under=90
```

## File Responsibilities

| File | Responsibility |
|---|---|
| `src/pedalpoint/config.py` | Load env vars into frozen Config dataclass |
| `src/pedalpoint/error_classifier.py` | Regex classify error strings → error type |
| `src/pedalpoint/circuit_breaker.py` | Pure fns for state transitions, expiry, backoff |
| `src/pedalpoint/server.py` | FastMCP app, lifespan, `local_llm` tool, `_call_local_llm` |
| `skills/route-tasks.md` | Claude instructions: routing, Context Courier, circuit breaker |
| `install.sh` | Install pkg, pull model, register MCP config, copy skill |

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

## Common Gotchas

- `get_config()` uses `lru_cache`. Tests must call `get_config.cache_clear()` before and after monkeypatching env vars.
- `_call_local_llm` is the testable core; `local_llm` (the MCP tool) just unwraps ctx and delegates to it.
- 402 errors trigger permanent fallback. 429 errors trigger retry-with-backoff only. Do not conflate them.
- The companion skill has no Python backing. Skill tests are manual scenarios in `tests/skill/scenarios/`.
