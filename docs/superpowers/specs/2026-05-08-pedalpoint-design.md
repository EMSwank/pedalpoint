# Pedalpoint — Design Specification

**Date:** 2026-05-08
**Status:** Approved
**Repo:** github.com/USERNAME/pedalpoint (open source)

---

## 1. Purpose

Pedalpoint is an open source MCP server + companion superpowers skill that lets Claude Code route mechanical development tasks (scaffolding, boilerplate, test stubs) to a local LLM (Ollama, LM Studio, Jan, or any OpenAI-compatible endpoint) instead of spawning Claude subagents for everything.

Goals:
- Reduce Claude API token consumption on mechanical work
- Continue development when Claude quota is exhausted (automatic fallback)
- Single install: MCP server + companion skill together
- Works across any codebase — no per-project configuration
- Claude decides routing automatically — no manual flagging by user

---

## 2. System Overview

```
Claude Code session
  │
  ├─ pedalpoint companion skill (~/.claude/plugins/pedalpoint/skills/route-tasks.md)
  │    ├─ reads .pedalpoint/state.json (circuit breaker state)
  │    ├─ classifies each task: mechanical → local_llm | judgment → Agent
  │    ├─ assembles context (Context Courier) before local_llm calls
  │    ├─ catches Agent quota errors → updates state.json → re-routes
  │    └─ probes Claude at HALF-OPEN → clears or doubles backoff
  │
  ├─ MCP server (Python, stdio transport)
  │    └─ tool: local_llm(prompt, system, model) → str
  │         └─ proxies to any OpenAI-compatible endpoint (Ollama default)
  │
  └─ .pedalpoint/
       ├─ state.json        (circuit breaker: CLOSED/OPEN/HALF-OPEN)
       └─ fallback-log.md   (human-readable audit trail of rerouted tasks)
```

**Configuration (env vars):**

| Variable | Default | Description |
|---|---|---|
| `PEDALPOINT_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint |
| `PEDALPOINT_MODEL` | `llama3` | Default local model |
| `PEDALPOINT_MODE` | `hybrid` | `hybrid` / `local-only` / `passthrough` |
| `PEDALPOINT_TIMEOUT` | `120` | Read timeout in seconds |
| `PEDALPOINT_INITIAL_FALLBACK_MINUTES` | `60` | Initial OPEN state duration; doubles on each probe failure (cap: 1440) |
| `PEDALPOINT_CONTEXT_LIMIT` | `16000` | Max chars injected as pattern context |

No daemon. No sidecar. No database. MCP server starts/stops with Claude Code session via stdio transport.

---

## 3. MCP Server

**Language:** Python 3.11+
**Framework:** `FastMCP` from `mcp` package
**HTTP client:** `httpx.AsyncClient` (async throughout)
**Transport:** stdio

### Async Design

Single `asyncio` event loop. `httpx.AsyncClient` created once at server startup via `lifespan` context manager — shared across all tool calls, closed cleanly on shutdown. No per-request client instantiation.

```python
@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=httpx.Timeout(connect=5.0, read=TIMEOUT, write=10.0, pool=5.0),
    ) as client:
        yield {"http": client}

mcp = FastMCP("pedalpoint", lifespan=lifespan)
```

### Tool Interface

```python
@mcp.tool()
async def local_llm(
    ctx,
    prompt: str,
    system: str | None = None,
    model: str | None = None,
) -> str
```

- `prompt`: full user message (may include injected pattern context)
- `system`: optional system prompt (skill sets coding-specific context)
- `model`: optional model override (falls back to `PEDALPOINT_MODEL`)

**No streaming.** MCP tool results are synchronous strings. `await client.post()` holds coroutine until full response. Local code-gen tasks don't require streaming; simplicity wins. Can add later via MCP resource streaming if needed.

### Timeout Strategy

| Timeout type | Value |
|---|---|
| Connect | 5s (Ollama is local — fast or down) |
| Read | `PEDALPOINT_TIMEOUT` default 120s (local LLMs can be slow) |
| Write | 10s (prompts may be large with injected context) |
| Pool | 5s |

### Error Mapping

| `httpx` exception | User-facing MCP error |
|---|---|
| `ConnectError` | "Ollama not reachable at `{BASE_URL}` — is it running?" |
| `TimeoutException` | "Model timed out after `{TIMEOUT}s` — increase `PEDALPOINT_TIMEOUT`" |
| `HTTPStatusError` | Forward HTTP status code + response body verbatim |

Errors surface as MCP tool errors. Claude Code displays them inline; skill catches and handles routing decisions.

---

## 4. Companion Skill — Routing Logic

**Location:** `~/.claude/plugins/pedalpoint/skills/route-tasks.md`
**Replaces:** `subagent-driven-development` (full replacement, not wrapper)
**Invocation:** `pedalpoint:route-tasks`

### Operating Modes

| Mode | Behavior |
|---|---|
| `hybrid` (default) | Claude classifies each task; mechanical → local_llm, judgment → Agent |
| `local-only` | All tasks → local_llm; zero Agent spawns (use when quota exhausted preemptively) |
| `passthrough` | All tasks → Agent spawns; pedalpoint inactive |

Set via `PEDALPOINT_MODE` env var. Skill reads at task execution time.

### Task Classification Heuristics

Claude applies these criteria to each task description before routing.

**Route to `local_llm` (mechanical):**
- Generate boilerplate matching established patterns in the codebase
- Write test stubs (function signatures only, no logic)
- Implement CRUD following existing examples
- Add type hints or docstrings to existing functions
- Generate config files from templates
- Repetitive serializers, validators, migrations following clear patterns
- Rename or move files per established conventions

**Route to Agent (judgment):**
- Architecture or design decisions
- Debugging — root cause unknown
- Cross-system integration
- Security-sensitive code (auth, payments, tokens, credentials)
- Performance optimization
- Code review or quality assessment
- Novel logic with no existing pattern to follow
- Anything requiring reading multiple files to understand context

**Escalation rule:** If no established pattern exists in the codebase for a mechanical task, escalate to Agent. Do not send pattern-free prompts to local LLM.

### Context Courier — Pattern Injection

Before every `local_llm` call, the skill must act as Context Courier:

1. Identify what established pattern applies to the task
2. Locate relevant example file(s) in the codebase via Read/grep
3. Extract focused excerpt (most relevant 30–50 lines — not whole file)
4. Assemble augmented prompt within `PEDALPOINT_CONTEXT_LIMIT` (default 16000 chars)
5. Call `local_llm(prompt=augmented, system=coding_context)`

**Augmented prompt structure:**
```
system:
  "You are a code generator. Follow the provided patterns exactly.
   Output only code. No explanation."

prompt:
  "## Existing pattern (src/api/posts.py lines 1-45):
   [excerpt]

   ## Task:
   [task description]
   Follow exact naming conventions, structure, and patterns above."
```

If no pattern found → escalate to Agent (not actually mechanical).

### Task Execution Decision Tree

```
read .pedalpoint/state.json
  │
  ├─ OPEN + not expired  → skip probe → local_llm (with context)
  ├─ OPEN + expired      → HALF-OPEN → probe Claude
  │    ├─ probe ok       → CLOSED → classify normally
  │    └─ probe fail     → OPEN (duration × 2) → local_llm
  │
  └─ CLOSED → classify task
       ├─ mechanical → local_llm (with context)
       └─ judgment  → try Agent
            ├─ success   → continue
            ├─ 429       → backoff + retry (30s → 60s → 120s); not fallback
            ├─ 402       → OPEN state (60min expiry) → local_llm
            └─ 529       → single-task local_llm; CLOSED next task
```

### Post-Session Review

If any tasks were rerouted during the session, skill prompts:
> "N tasks ran on local LLM during fallback. Run Claude review pass now?"

If yes: spawns Agent to review `.pedalpoint/fallback-log.md` + `git diff` of all changes made during fallback period.

---

## 5. Circuit Breaker — State Machine

### States

| State | Meaning |
|---|---|
| `CLOSED` | Normal. Try Claude first. |
| `OPEN` | Quota exhausted. Route all tasks to local LLM. |
| `HALF-OPEN` | Probe period after expiry. One test call to Claude. |

### State File: `.pedalpoint/state.json`

```json
{
  "circuit": "open",
  "reason": "402_quota",
  "opened_at": "2026-05-08T15:30:00Z",
  "expires": "2026-05-08T16:30:00Z",
  "failure_count": 1,
  "fallback_duration_minutes": 60,
  "tasks_rerouted": 3
}
```

CLOSED state: `{"circuit": "closed"}` or file absent.

### Error Classification (regex against Agent spawn output)

| Match pattern | Type | Action |
|---|---|---|
| `429` / `rate.?limit` | Transient rate limit | Retry: 30s → 60s → 120s (max 3); then single-task local fallback |
| `402` / `quota` / `billing` / `insufficient` | Hard quota exhausted | → OPEN, 60min expiry |
| `529` / `overload` / `capacity` | Server overloaded | Single-task local fallback; CLOSED next task |
| `timeout` / `connection` | Network error | One retry; then treat as 529 |

### Exponential Backoff on OPEN Duration

| `failure_count` | `fallback_duration_minutes` |
|---|---|
| 1 | 60 |
| 2 | 120 |
| 3 | 240 |
| N | `min(60 × 2^(N-1), 1440)` — capped at 24h |

### Transitions

```
CLOSED ──[402 quota]──► OPEN ──[expires passed]──► HALF-OPEN
  ▲                                                     │
  └──────────────[probe success]───────────────────────┘
                                                        │
  OPEN ◄──────────────[probe fail → duration × 2]──────┘
```

HALF-OPEN probe: minimal Agent spawn (`"Respond with only the word ok"`).
- Success → write `{"circuit":"closed"}`
- 402 failure → write OPEN with doubled duration, increment `failure_count`
- 429 failure → not a quota issue; wait for rate limit, re-probe

**Read timing:** Skill reads `state.json` before each task (not once per session). **Write mechanism:** Skill instructs Claude to write `state.json` via the `Write` tool — the MCP server never touches this file. Concurrent sessions: last-write-wins acceptable — both write same OPEN transition.

### Fallback Log: `.pedalpoint/fallback-log.md`

```markdown
## 2026-05-08T15:42:00Z — task rerouted (reason: 402_quota)
**Task:** Generate CRUD endpoints for UserProfile model
**Local LLM response:** [response here]
---
```

---

## 6. Install Script

### One-liner

```bash
curl -fsSL https://raw.githubusercontent.com/USERNAME/pedalpoint/main/install.sh | sh
```

With options:
```bash
curl -fsSL .../install.sh | sh -s -- --model mistral --base-url http://localhost:11434/v1
```

### Flow

1. **Preflight checks**
   - Python 3.11+ (fail if missing)
   - `curl` or `git` (fail if missing)
   - Ollama reachable at `base_url` (warn only — don't fail)

2. **Detect package manager** — prefer: `uv tool install` > `pipx install` > `pip install --user`

3. **Install Python package** → `pedalpoint-server` binary lands in PATH

4. **Install companion skill**
   - Copy `skills/route-tasks.md` → `~/.claude/plugins/pedalpoint/skills/`
   - Copy plugin manifest → `~/.claude/plugins/pedalpoint/`

5. **Register MCP server in `~/.claude/mcp.json`**
   - `jq` merge (not overwrite — preserves other servers)
   - Injects env vars from flags or defaults

6. **Create `~/.pedalpoint/` directory**

7. **Print summary + restart reminder**

### MCP Config Entry

```json
{
  "mcpServers": {
    "pedalpoint": {
      "command": "pedalpoint-server",
      "args": [],
      "env": {
        "PEDALPOINT_BASE_URL": "http://localhost:11434/v1",
        "PEDALPOINT_MODEL": "llama3",
        "PEDALPOINT_MODE": "hybrid",
        "PEDALPOINT_TIMEOUT": "120"
      }
    }
  }
}
```

**Idempotent:** Re-running updates skill files and env vars — never duplicates MCP entry.
**Uninstall:** `install.sh --uninstall` reverses all steps; prompts before removing `~/.pedalpoint/`.
**Platform:** macOS + Linux. Windows out of scope.

---

## 7. Testing Strategy

**Framework:** `pytest` + `pytest-asyncio` + `respx` (httpx mock)
**Methodology:** TDD — test first, implement second. All PRs require passing tests.

### Test Structure

```
tests/
  unit/
    test_server.py           # tool handler, request construction, error mapping
    test_circuit_breaker.py  # all state transitions (100% coverage required)
    test_error_classifier.py # regex patterns per error type
    test_config.py           # env var parsing, defaults
  integration/
    test_ollama.py           # requires live Ollama (opt-in)
  skill/
    scenarios/
      mechanical_routing.md
      judgment_routing.md
      fallback_trigger.md
      probe_success.md
      probe_failure.md
```

### Unit Tests

**MCP server:** Mock httpx via `respx`. Test: tool handler invocation, system prompt inclusion, model override, all error types, timeout config.

**Error classifier (100% coverage):**
```python
@pytest.mark.parametrize("text,expected", [
    ("402 insufficient_quota",     "hard_quota"),
    ("429 rate limit exceeded",    "rate_limit"),
    ("529 server overloaded",      "overload"),
    ("connection timeout",         "network"),
    ("billing hard limit reached", "hard_quota"),
])
def test_classify_error(text, expected):
    assert classify_error(text) == expected
```

**Circuit breaker (100% coverage):** All 6 transitions. Exponential backoff: `failure_count` 1→2→3 produces 60→120→240 minutes. Cap at 1440 verified.

### Integration Tests

Opt-in: `PEDALPOINT_INTEGRATION=true pytest tests/integration/`
CI: GitHub Actions with official Ollama Docker image. Unit tests always run; integration gated on service.

### Skill Tests

Markdown instructions cannot be unit tested mechanically. Each scenario document specifies: task input, expected classification, expected tool called, verification steps. Run manually before merging skill changes.

### Coverage Targets

| Component | Target |
|---|---|
| MCP server | ≥ 90% |
| Circuit breaker | 100% |
| Error classifier | 100% |

### pytest Config

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "integration: requires live Ollama — set PEDALPOINT_INTEGRATION=true",
]
```

---

## 8. Project Structure

```
pedalpoint/
  src/pedalpoint/
    __init__.py
    server.py          # FastMCP app, lifespan, tool handler
    config.py          # env var parsing, defaults
    error_classifier.py # regex-based error type detection
  skills/
    route-tasks.md     # companion superpowers skill
  tests/
    unit/
    integration/
    skill/scenarios/
  docs/superpowers/specs/
    2026-05-08-pedalpoint-design.md
  install.sh
  pyproject.toml
  README.md
  CLAUDE.md
```

---

## 9. Open Questions / Out of Scope

**Out of scope (v1):**
- Windows support
- Streaming responses from local LLM
- Per-project skill configuration (global only)
- Web UI for fallback log
- Multiple local LLM endpoints (single `base_url` only)

**Deferred:**
- `pedalpoint:review-fallback` as standalone skill (v2)
- Automatic model selection by task type (v2)
- Token usage tracking and reporting (v2)
