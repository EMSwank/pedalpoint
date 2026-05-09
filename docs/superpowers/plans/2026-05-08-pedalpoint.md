# Pedalpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `pedalpoint:route-tasks` (once installed) or `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MCP server + companion superpowers skill that routes mechanical dev tasks to a local LLM (Ollama) and automatically falls back to local-only mode when Claude quota is exhausted.

**Architecture:** Thin Python MCP server (FastMCP + httpx) exposes a single `local_llm(prompt, system, model)` tool that proxies to any OpenAI-compatible endpoint. A companion skill (`pedalpoint:route-tasks`) replaces `subagent-driven-development`, classifying each task and routing it appropriately. Circuit breaker state lives in `~/.pedalpoint/state.json`; the skill reads/writes it via Claude's Write tool — the server never touches it.

**Tech Stack:** Python 3.11+, `mcp` (FastMCP), `httpx`, `pytest`, `pytest-asyncio`, `respx`, `pyproject.toml` (hatchling), GitHub Actions

---

## File Map

```
pedalpoint/
  src/pedalpoint/
    __init__.py          empty package marker
    config.py            load_config() → Config dataclass from env vars
    error_classifier.py  classify_error(text) → "hard_quota"|"rate_limit"|"overload"|"network"|"unknown"
    circuit_breaker.py   pure fns: read_state, write_state, transition_to_open/closed, double_duration, etc.
    server.py            FastMCP app + lifespan + local_llm tool + _call_local_llm (testable core)
  skills/
    route-tasks.md       companion superpowers skill (Markdown instructions for Claude)
  tests/
    __init__.py
    unit/
      __init__.py
      test_config.py
      test_error_classifier.py
      test_circuit_breaker.py
      test_server.py
    integration/
      __init__.py
      test_ollama.py
    skill/
      scenarios/
        mechanical_routing.md
        judgment_routing.md
        fallback_trigger.md
        probe_success.md
        probe_failure.md
  .github/workflows/
    ci.yml
  install.sh
  pyproject.toml
  .gitignore
  README.md
  CLAUDE.md
```

---

## Task 0: Merge docs/initial-design → main

**Files:** none (git operations only)

- [ ] **Step 1: Merge to main**

```bash
git checkout main 2>/dev/null || git checkout -b main
git merge docs/initial-design --no-ff -m "docs: add design spec and implementation plan"
```

Expected: fast-forward or merge commit on main with `docs/` directory.

- [ ] **Step 2: Verify**

```bash
git log --oneline -5
ls docs/superpowers/specs/
ls docs/superpowers/plans/
```

Expected: both spec and plan files present.

---

## Task 1: Project Scaffolding

**Branch:** `chore/scaffolding`

**Files:**
- Create: `pyproject.toml`
- Create: `src/pedalpoint/__init__.py`
- Create: `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b chore/scaffolding
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pedalpoint"
version = "0.1.0"
description = "MCP server that routes mechanical dev tasks to a local LLM"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.27.0",
]

[project.scripts]
pedalpoint-server = "pedalpoint.server:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "respx>=0.21.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.4.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/pedalpoint"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "integration: requires live Ollama — set PEDALPOINT_INTEGRATION=true",
]
testpaths = ["tests"]

[tool.coverage.run]
source = ["src/pedalpoint"]

[tool.coverage.report]
fail_under = 90
show_missing = true

[tool.ruff]
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I"]
```

- [ ] **Step 3: Create directory structure and empty __init__ files**

```bash
mkdir -p src/pedalpoint
mkdir -p tests/unit
mkdir -p tests/integration
mkdir -p tests/skill/scenarios
mkdir -p skills
mkdir -p .github/workflows
touch src/pedalpoint/__init__.py
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py
```

- [ ] **Step 4: Create .gitignore**

```
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
venv/
.pytest_cache/
.coverage
htmlcov/
*.log
.env
```

- [ ] **Step 5: Install dev dependencies**

```bash
pip install -e ".[dev]"
```

Expected: no errors. `pedalpoint-server` command available (will fail until server.py exists).

- [ ] **Step 6: Verify pytest discovers tests (empty)**

```bash
pytest tests/ -v
```

Expected: `no tests ran` or `0 passed`.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/ tests/ skills/ .github/ .gitignore
git commit -m "chore: scaffold project structure, pyproject.toml, test layout"
```

---

## Task 2: Config Module

**Branch:** `feat/config`

**Files:**
- Create: `src/pedalpoint/config.py`
- Create: `tests/unit/test_config.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b feat/config
```

- [ ] **Step 2: Write failing tests first**

Create `tests/unit/test_config.py`:

```python
import os
import pytest
from pedalpoint.config import Config, get_config


def test_defaults(monkeypatch):
    for key in [
        "PEDALPOINT_BASE_URL", "PEDALPOINT_MODEL", "PEDALPOINT_MODE",
        "PEDALPOINT_TIMEOUT", "PEDALPOINT_INITIAL_FALLBACK_MINUTES",
        "PEDALPOINT_CONTEXT_LIMIT",
    ]:
        monkeypatch.delenv(key, raising=False)
    get_config.cache_clear()
    cfg = get_config()
    assert cfg.base_url == "http://localhost:11434/v1"
    assert cfg.model == "gemma4:e4b"
    assert cfg.mode == "hybrid"
    assert cfg.timeout == 120.0
    assert cfg.initial_fallback_minutes == 60
    assert cfg.context_limit == 16000
    get_config.cache_clear()


def test_custom_base_url(monkeypatch):
    monkeypatch.setenv("PEDALPOINT_BASE_URL", "http://localhost:1234/v1")
    get_config.cache_clear()
    assert get_config().base_url == "http://localhost:1234/v1"
    get_config.cache_clear()


def test_custom_model(monkeypatch):
    monkeypatch.setenv("PEDALPOINT_MODEL", "llama3")
    get_config.cache_clear()
    assert get_config().model == "llama3"
    get_config.cache_clear()


def test_custom_timeout(monkeypatch):
    monkeypatch.setenv("PEDALPOINT_TIMEOUT", "30")
    get_config.cache_clear()
    assert get_config().timeout == 30.0
    get_config.cache_clear()


def test_custom_fallback_minutes(monkeypatch):
    monkeypatch.setenv("PEDALPOINT_INITIAL_FALLBACK_MINUTES", "30")
    get_config.cache_clear()
    assert get_config().initial_fallback_minutes == 30
    get_config.cache_clear()


def test_custom_context_limit(monkeypatch):
    monkeypatch.setenv("PEDALPOINT_CONTEXT_LIMIT", "8000")
    get_config.cache_clear()
    assert get_config().context_limit == 8000
    get_config.cache_clear()


def test_config_is_frozen():
    get_config.cache_clear()
    cfg = get_config()
    with pytest.raises((AttributeError, TypeError)):
        cfg.model = "other"  # type: ignore
    get_config.cache_clear()
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
pytest tests/unit/test_config.py -v
```

Expected: `ImportError` or `ModuleNotFoundError: No module named 'pedalpoint.config'`

- [ ] **Step 4: Implement config.py**

Create `src/pedalpoint/config.py`:

```python
import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Config:
    base_url: str
    model: str
    mode: str
    timeout: float
    initial_fallback_minutes: int
    context_limit: int


@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config(
        base_url=os.getenv("PEDALPOINT_BASE_URL", "http://localhost:11434/v1"),
        model=os.getenv("PEDALPOINT_MODEL", "gemma4:e4b"),
        mode=os.getenv("PEDALPOINT_MODE", "hybrid"),
        timeout=float(os.getenv("PEDALPOINT_TIMEOUT", "120")),
        initial_fallback_minutes=int(
            os.getenv("PEDALPOINT_INITIAL_FALLBACK_MINUTES", "60")
        ),
        context_limit=int(os.getenv("PEDALPOINT_CONTEXT_LIMIT", "16000")),
    )
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
pytest tests/unit/test_config.py -v
```

Expected: `7 passed`

- [ ] **Step 6: Check coverage**

```bash
pytest tests/unit/test_config.py --cov=pedalpoint.config --cov-report=term-missing
```

Expected: 100% coverage on config.py

- [ ] **Step 7: Commit**

```bash
git add src/pedalpoint/config.py tests/unit/test_config.py
git commit -m "feat: add config module with env var loading and lru_cache"
```

---

## Task 3: Error Classifier

**Branch:** `feat/error-classifier`

**Files:**
- Create: `src/pedalpoint/error_classifier.py`
- Create: `tests/unit/test_error_classifier.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b feat/error-classifier
```

- [ ] **Step 2: Write failing tests**

Create `tests/unit/test_error_classifier.py`:

```python
import pytest
from pedalpoint.error_classifier import classify_error


@pytest.mark.parametrize("text,expected", [
    # hard_quota — 402 and variants
    ("402 Payment Required",            "hard_quota"),
    ("402 insufficient_quota",          "hard_quota"),
    ("quota exceeded",                  "hard_quota"),
    ("billing hard limit reached",      "hard_quota"),
    ("insufficient credits",            "hard_quota"),
    ("You have exceeded your quota",    "hard_quota"),
    # rate_limit — 429 and variants
    ("429 Too Many Requests",           "rate_limit"),
    ("rate limit exceeded",             "rate_limit"),
    ("rate-limit",                      "rate_limit"),
    ("RateLimit hit",                   "rate_limit"),
    # overload — 529 and variants
    ("529 server overloaded",           "overload"),
    ("The server is overloaded",        "overload"),
    ("service capacity exceeded",       "overload"),
    # network
    ("connection timeout",              "network"),
    ("Connection refused",              "network"),
    ("Read timeout",                    "network"),
    # unknown
    ("some unrecognized error message", "unknown"),
    ("500 Internal Server Error",       "unknown"),
])
def test_classify_error(text: str, expected: str) -> None:
    assert classify_error(text) == expected


def test_case_insensitive_quota() -> None:
    assert classify_error("QUOTA EXCEEDED") == "hard_quota"


def test_case_insensitive_rate_limit() -> None:
    assert classify_error("RATE LIMIT") == "rate_limit"


def test_hard_quota_takes_priority_over_rate_limit() -> None:
    # If a message somehow contains both, hard_quota wins (checked first)
    assert classify_error("402 rate limit quota") == "hard_quota"
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
pytest tests/unit/test_error_classifier.py -v
```

Expected: `ImportError: cannot import name 'classify_error'`

- [ ] **Step 4: Implement error_classifier.py**

Create `src/pedalpoint/error_classifier.py`:

```python
import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"402|quota|billing|insufficient", re.IGNORECASE), "hard_quota"),
    (re.compile(r"429|rate.?limit", re.IGNORECASE), "rate_limit"),
    (re.compile(r"529|overload|capacity", re.IGNORECASE), "overload"),
    (re.compile(r"timeout|connection", re.IGNORECASE), "network"),
]


def classify_error(text: str) -> str:
    """Return the error category for a given error message string."""
    for pattern, error_type in _PATTERNS:
        if pattern.search(text):
            return error_type
    return "unknown"
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
pytest tests/unit/test_error_classifier.py -v
```

Expected: `21 passed`

- [ ] **Step 6: Check coverage**

```bash
pytest tests/unit/test_error_classifier.py --cov=pedalpoint.error_classifier --cov-report=term-missing
```

Expected: 100%

- [ ] **Step 7: Commit**

```bash
git add src/pedalpoint/error_classifier.py tests/unit/test_error_classifier.py
git commit -m "feat: add regex-based error classifier (hard_quota/rate_limit/overload/network)"
```

---

## Task 4: Circuit Breaker Utilities

**Branch:** `feat/circuit-breaker`

**Files:**
- Create: `src/pedalpoint/circuit_breaker.py`
- Create: `tests/unit/test_circuit_breaker.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b feat/circuit-breaker
```

- [ ] **Step 2: Write failing tests**

Create `tests/unit/test_circuit_breaker.py`:

```python
import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pedalpoint.circuit_breaker import (
    CLOSED_STATE,
    compute_duration,
    double_duration,
    increment_rerouted,
    is_expired,
    read_state,
    transition_to_closed,
    transition_to_open,
    write_state,
)


# --- read_state ---

def test_read_state_absent_returns_closed(tmp_path: Path) -> None:
    assert read_state(tmp_path / "state.json") == {"circuit": "closed"}


def test_read_state_valid(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    data = {"circuit": "open", "failure_count": 2}
    p.write_text(json.dumps(data))
    assert read_state(p) == data


def test_read_state_corrupted_returns_closed(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    p.write_text("not valid json {{{")
    assert read_state(p) == {"circuit": "closed"}


# --- write_state ---

def test_write_state_creates_file(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    write_state({"circuit": "closed"}, p)
    assert json.loads(p.read_text()) == {"circuit": "closed"}


def test_write_state_creates_parent_dirs(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "dir" / "state.json"
    write_state({"circuit": "closed"}, p)
    assert p.exists()


def test_write_state_overwrites_existing(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    write_state({"circuit": "open", "failure_count": 1}, p)
    write_state({"circuit": "closed"}, p)
    assert json.loads(p.read_text()) == {"circuit": "closed"}


# --- compute_duration ---

def test_compute_duration_failure_1() -> None:
    assert compute_duration(1) == 60


def test_compute_duration_failure_2() -> None:
    assert compute_duration(2) == 120


def test_compute_duration_failure_3() -> None:
    assert compute_duration(3) == 240


def test_compute_duration_failure_4() -> None:
    assert compute_duration(4) == 480


def test_compute_duration_caps_at_1440() -> None:
    assert compute_duration(100) == 1440


def test_compute_duration_custom_initial() -> None:
    assert compute_duration(1, initial_minutes=30) == 30
    assert compute_duration(2, initial_minutes=30) == 60


# --- is_expired ---

def test_is_expired_future() -> None:
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert not is_expired({"expires": expires})


def test_is_expired_past() -> None:
    expires = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    assert is_expired({"expires": expires})


def test_is_expired_missing_key() -> None:
    assert is_expired({})


# --- transition_to_open ---

def test_transition_to_open_sets_circuit() -> None:
    state = transition_to_open("402_quota")
    assert state["circuit"] == "open"


def test_transition_to_open_sets_reason() -> None:
    state = transition_to_open("402_quota")
    assert state["reason"] == "402_quota"


def test_transition_to_open_failure_count_default() -> None:
    state = transition_to_open("402_quota")
    assert state["failure_count"] == 1


def test_transition_to_open_duration_60_for_count_1() -> None:
    state = transition_to_open("402_quota", failure_count=1)
    assert state["fallback_duration_minutes"] == 60


def test_transition_to_open_expires_in_future() -> None:
    state = transition_to_open("402_quota")
    expires = datetime.fromisoformat(state["expires"])
    assert expires > datetime.now(timezone.utc)


def test_transition_to_open_tasks_rerouted() -> None:
    state = transition_to_open("402_quota", tasks_rerouted=5)
    assert state["tasks_rerouted"] == 5


# --- transition_to_closed ---

def test_transition_to_closed() -> None:
    assert transition_to_closed() == {"circuit": "closed"}


# --- double_duration ---

def test_double_duration_increments_failure_count() -> None:
    state = transition_to_open("402_quota", failure_count=1)
    doubled = double_duration(state)
    assert doubled["failure_count"] == 2


def test_double_duration_doubles_minutes() -> None:
    state = transition_to_open("402_quota", failure_count=1)
    doubled = double_duration(state)
    assert doubled["fallback_duration_minutes"] == 120


def test_double_duration_preserves_reason() -> None:
    state = transition_to_open("402_quota")
    doubled = double_duration(state)
    assert doubled["reason"] == "402_quota"


def test_double_duration_caps_at_1440() -> None:
    state = transition_to_open("402_quota", failure_count=10)
    doubled = double_duration(state)
    assert doubled["fallback_duration_minutes"] == 1440


# --- increment_rerouted ---

def test_increment_rerouted_starts_at_zero() -> None:
    state = transition_to_open("402_quota")
    assert state.get("tasks_rerouted", 0) == 0
    updated = increment_rerouted(state)
    assert updated["tasks_rerouted"] == 1


def test_increment_rerouted_accumulates() -> None:
    state = transition_to_open("402_quota")
    state = increment_rerouted(state)
    state = increment_rerouted(state)
    assert state["tasks_rerouted"] == 2
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
pytest tests/unit/test_circuit_breaker.py -v
```

Expected: `ImportError: cannot import name 'read_state'`

- [ ] **Step 4: Implement circuit_breaker.py**

Create `src/pedalpoint/circuit_breaker.py`:

```python
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CircuitState = dict[str, Any]

CLOSED_STATE: CircuitState = {"circuit": "closed"}

DEFAULT_STATE_PATH = Path.home() / ".pedalpoint" / "state.json"


def read_state(path: Path = DEFAULT_STATE_PATH) -> CircuitState:
    if not path.exists():
        return CLOSED_STATE.copy()
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return CLOSED_STATE.copy()


def write_state(state: CircuitState, path: Path = DEFAULT_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(path)


def compute_duration(failure_count: int, initial_minutes: int = 60) -> int:
    return min(initial_minutes * (2 ** (failure_count - 1)), 1440)


def is_expired(state: CircuitState) -> bool:
    expires = state.get("expires")
    if not expires:
        return True
    return datetime.now(timezone.utc) >= datetime.fromisoformat(expires)


def transition_to_open(
    reason: str,
    failure_count: int = 1,
    initial_minutes: int = 60,
    tasks_rerouted: int = 0,
) -> CircuitState:
    now = datetime.now(timezone.utc)
    duration = compute_duration(failure_count, initial_minutes)
    return {
        "circuit": "open",
        "reason": reason,
        "opened_at": now.isoformat(),
        "expires": (now + timedelta(minutes=duration)).isoformat(),
        "failure_count": failure_count,
        "fallback_duration_minutes": duration,
        "tasks_rerouted": tasks_rerouted,
    }


def transition_to_closed() -> CircuitState:
    return CLOSED_STATE.copy()


def double_duration(
    state: CircuitState, initial_minutes: int = 60
) -> CircuitState:
    failure_count = state.get("failure_count", 1) + 1
    return transition_to_open(
        reason=state.get("reason", "unknown"),
        failure_count=failure_count,
        initial_minutes=initial_minutes,
        tasks_rerouted=state.get("tasks_rerouted", 0),
    )


def increment_rerouted(state: CircuitState) -> CircuitState:
    return {**state, "tasks_rerouted": state.get("tasks_rerouted", 0) + 1}
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
pytest tests/unit/test_circuit_breaker.py -v
```

Expected: `42 passed` (approximately — exact count depends on parametrize expansion)

- [ ] **Step 6: Check coverage**

```bash
pytest tests/unit/test_circuit_breaker.py --cov=pedalpoint.circuit_breaker --cov-report=term-missing
```

Expected: 100%

- [ ] **Step 7: Commit**

```bash
git add src/pedalpoint/circuit_breaker.py tests/unit/test_circuit_breaker.py
git commit -m "feat: add circuit breaker utilities (state transitions, expiry, exponential backoff)"
```

---

## Task 5: MCP Server

**Branch:** `feat/mcp-server`

**Files:**
- Create: `src/pedalpoint/server.py`
- Create: `tests/unit/test_server.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b feat/mcp-server
```

Note: This branch needs config.py from Task 2. Either merge `feat/config` to main first, or cherry-pick. Recommended: merge all preceding feat/* branches to main before starting this task.

- [ ] **Step 2: Write failing tests**

Create `tests/unit/test_server.py`:

```python
import pytest
import httpx
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
        result = await _call_local_llm(client, "write foo", None, "gemma4:e4b", TEST_CFG)
    assert result == "def foo(): pass"


@respx.mock
@pytest.mark.asyncio
async def test_system_prompt_included_in_messages() -> None:
    route = respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=MOCK_RESPONSE)
    )
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        await _call_local_llm(client, "write foo", "be terse", "gemma4:e4b", TEST_CFG)
    body = route.calls[0].request.content
    import json
    payload = json.loads(body)
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
    body = route.calls[0].request.content
    import json
    payload = json.loads(body)
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
    import json
    payload = json.loads(route.calls[0].request.content)
    assert payload["model"] == "llama3"


@pytest.mark.asyncio
async def test_connect_error_raises_clear_message() -> None:
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        with respx.mock:
            respx.post("http://localhost:11434/v1/chat/completions").mock(
                side_effect=httpx.ConnectError("refused")
            )
            with pytest.raises(ValueError, match="Ollama not reachable"):
                await _call_local_llm(client, "prompt", None, "gemma4:e4b", TEST_CFG)


@pytest.mark.asyncio
async def test_timeout_raises_clear_message() -> None:
    async with httpx.AsyncClient(base_url="http://localhost:11434/v1") as client:
        with respx.mock:
            respx.post("http://localhost:11434/v1/chat/completions").mock(
                side_effect=httpx.TimeoutException("timed out")
            )
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
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
pytest tests/unit/test_server.py -v
```

Expected: `ImportError: cannot import name '_call_local_llm'`

- [ ] **Step 4: Implement server.py**

Create `src/pedalpoint/server.py`:

```python
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
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
pytest tests/unit/test_server.py -v
```

Expected: `8 passed`

- [ ] **Step 6: Check coverage**

```bash
pytest tests/unit/test_server.py --cov=pedalpoint.server --cov-report=term-missing
```

Expected: ≥90% (the `main()` and MCP tool wrapper are hard to unit-test without a full MCP runtime)

- [ ] **Step 7: Verify `pedalpoint-server` entry point is wired**

```bash
pedalpoint-server --help 2>&1 | head -5 || echo "entry point reachable"
```

Expected: no ImportError (may print MCP usage or just exit)

- [ ] **Step 8: Commit**

```bash
git add src/pedalpoint/server.py tests/unit/test_server.py
git commit -m "feat: add MCP server with local_llm tool, async httpx client, typed error messages"
```

---

## Task 6: Integration Test Scaffold

**Branch:** `test/integration`

**Files:**
- Create: `tests/integration/test_ollama.py`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b test/integration
```

- [ ] **Step 2: Create integration test file**

Create `tests/integration/test_ollama.py`:

```python
import os
import pytest
import httpx

from pedalpoint.config import get_config
from pedalpoint.server import _call_local_llm

pytestmark = pytest.mark.integration


@pytest.fixture
def cfg():
    get_config.cache_clear()
    c = get_config()
    get_config.cache_clear()
    return c


@pytest.mark.skipif(
    not os.getenv("PEDALPOINT_INTEGRATION"),
    reason="Set PEDALPOINT_INTEGRATION=true to run",
)
@pytest.mark.asyncio
async def test_ollama_reachable(cfg) -> None:
    async with httpx.AsyncClient(
        base_url=cfg.base_url,
        timeout=httpx.Timeout(connect=5.0, read=cfg.timeout, write=10.0, pool=5.0),
    ) as client:
        resp = await client.get("/models")
    assert resp.status_code == 200


@pytest.mark.skipif(
    not os.getenv("PEDALPOINT_INTEGRATION"),
    reason="Set PEDALPOINT_INTEGRATION=true to run",
)
@pytest.mark.asyncio
async def test_local_llm_returns_nonempty_string(cfg) -> None:
    async with httpx.AsyncClient(
        base_url=cfg.base_url,
        timeout=httpx.Timeout(connect=5.0, read=cfg.timeout, write=10.0, pool=5.0),
    ) as client:
        result = await _call_local_llm(
            client,
            "Write a Python function that returns 42. Output only code.",
            "You are a code generator. Output only code, no explanation.",
            cfg.model,
            cfg,
        )
    assert isinstance(result, str)
    assert len(result) > 0
```

- [ ] **Step 3: Verify integration tests skip without flag**

```bash
pytest tests/integration/ -v
```

Expected: `2 skipped` (not failed, not error)

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_ollama.py
git commit -m "test: add opt-in integration tests for live Ollama"
```

---

## Task 7: Companion Skill

**Branch:** `feat/companion-skill`

**Files:**
- Create: `skills/route-tasks.md`
- Create: `tests/skill/scenarios/mechanical_routing.md`
- Create: `tests/skill/scenarios/judgment_routing.md`
- Create: `tests/skill/scenarios/fallback_trigger.md`
- Create: `tests/skill/scenarios/probe_success.md`
- Create: `tests/skill/scenarios/probe_failure.md`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b feat/companion-skill
```

- [ ] **Step 2: Create the companion skill**

Create `skills/route-tasks.md`:

```markdown
---
name: route-tasks
description: Execute implementation plan tasks with automatic routing between local LLM and Claude. Replaces subagent-driven-development with quota-aware circuit-breaker routing. Use when executing any implementation plan in a pedalpoint-enabled project.
---

# Pedalpoint: Intelligent Task Router

You are executing an implementation plan. For each task, follow these steps exactly.

## Prerequisites Check

Verify the `local_llm` MCP tool is available. If it is not listed in your available tools, warn the user that the pedalpoint MCP server is not running and fall back to Agent for all tasks.

Check `PEDALPOINT_MODE` environment variable:
- `local-only` → skip Step 2 classification, route ALL tasks through Step 3 (Context Courier) to local_llm
- `passthrough` → skip Steps 2–4, route ALL tasks to Agent spawns
- `hybrid` (default or unset) → follow normal flow below

---

## Step 1: Read Circuit Breaker State

Before executing each task, run:

```bash
cat ~/.pedalpoint/state.json 2>/dev/null || echo '{"circuit":"closed"}'
```

Parse the JSON:

**If `circuit` is `"closed"` or file absent:** proceed to Step 2.

**If `circuit` is `"open"`:**
- Check `expires` field vs current time (`date -u +%Y-%m-%dT%H:%M:%SZ`)
- If current time < expires: skip to Step 4 (local_llm, no classification)
- If current time >= expires: proceed to Step 1b (HALF-OPEN probe)

### Step 1b: HALF-OPEN Probe

Spawn a minimal Agent with prompt: `"Respond with only the word ok"`.

- **Agent succeeds:** Write `{"circuit":"closed"}` to `~/.pedalpoint/state.json`. Proceed to Step 2.
- **Agent fails with 402/quota/billing/insufficient:** Read existing state, double the `fallback_duration_minutes` and increment `failure_count`, write updated OPEN state. Proceed to Step 4.
- **Agent fails with 429/rate-limit:** Wait 30 seconds. Retry probe once. If still failing, treat as transient — proceed to Step 2.

---

## Step 2: Classify the Task

Read the task description. Apply these rules:

### Route to `local_llm` (mechanical) when ALL apply:
- Generates code that matches an established pattern already in the codebase
- No architectural decision required
- No cross-system integration
- No security-sensitive logic (auth, payments, tokens, credentials)
- Pattern can be verified by grep/Read (see Step 3)

**Examples:** generate CRUD following an existing CRUD file, write test function stubs, add type hints to existing functions, generate a config file following an existing template, write a serializer matching the existing serializer pattern.

### Route to Agent (judgment) when ANY applies:
- Architecture or design decision required
- Debugging with unknown root cause
- Cross-system integration
- Security-sensitive code
- Novel logic — no existing codebase pattern
- Requires reading multiple files to understand what to build

**When in doubt: route to Agent.**

---

## Step 3: Context Courier (mechanical tasks only)

You MUST gather pattern context before calling `local_llm`. Do not assume a pattern exists — verify it.

1. Identify the pattern type from the task (CRUD, serializer, test stub, migration, etc.)
2. Search the codebase:
   ```bash
   grep -r "<relevant keyword>" src/ --include="*.py" -l 2>/dev/null
   ```
3. **Check the result explicitly:**
   - **No files returned / empty output:** The task is not actually mechanical. Escalate to Agent (Step 4b, judgment path). Do not proceed with local_llm.
   - **Files returned:** Read the most relevant file. Extract 30–50 lines of the closest matching example.

4. Assemble the augmented prompt. Keep total length under 16000 characters:

   ```
   system: "You are a code generator. Follow the provided patterns exactly. Output only code. No explanation."

   prompt: |
     ## Existing pattern (<filepath> lines <N>-<M>):
     <excerpt from file>

     ## Task:
     <task description>
     Follow the exact naming conventions, structure, and patterns shown above.
   ```

5. Proceed to Step 4 (local_llm execution path).

---

## Step 4: Execute the Task

### Mechanical path (local_llm)

Call the `local_llm` tool with the augmented prompt from Step 3:
```
local_llm(prompt=<augmented prompt>, system="You are a code generator. Follow the provided patterns exactly. Output only code. No explanation.")
```

Apply the returned string:
1. `git checkout -b feat/<task-slug>` (or appropriate branch prefix)
2. Write the returned code to the target file using Write/Edit tools
3. Run the test suite: `pytest tests/ -x -q`
4. If tests fail with trivial issues (missing import, typo): fix inline. If non-trivial: escalate to Agent.
5. Commit using Conventional Commits format
6. Mark task complete in the plan

Log this task to `~/.pedalpoint/fallback-log.md` only if circuit is OPEN (fallback active).

### Judgment path (Agent)

Spawn an Agent with:
- The full task description
- Relevant file paths from the plan
- Any context from previous tasks that affects this one
- Instruction to follow existing codebase patterns

Monitor the Agent spawn result. On error, proceed to Step 4b.

### Step 4b: Agent Error Handling

Parse the error text from the failed Agent spawn:

| Error pattern | Action |
|---|---|
| `429` or `rate.?limit` | Wait 30s, retry (up to 3 times). After 3 failures: route this task only to local_llm (circuit stays CLOSED) |
| `402`, `quota`, `billing`, `insufficient` | Write OPEN state to `~/.pedalpoint/state.json` (see below). Re-route this task to local_llm via Step 3. |
| `529`, `overload`, `capacity` | Route this task only to local_llm. Circuit stays CLOSED for next task. |
| `timeout`, `connection` | Retry once. If still failing, treat as 529. |

**Writing OPEN state** (on 402 quota error):
```json
{
  "circuit": "open",
  "reason": "402_quota",
  "opened_at": "<current UTC ISO timestamp>",
  "expires": "<current UTC + 60 minutes ISO timestamp>",
  "failure_count": 1,
  "fallback_duration_minutes": 60,
  "tasks_rerouted": 0
}
```
Write this to `~/.pedalpoint/state.json` using the Write tool.

**Logging rerouted tasks** — append to `~/.pedalpoint/fallback-log.md`:
```markdown
## <ISO timestamp> — task rerouted (reason: <reason>)
**Task:** <task description>
**Response preview:** <first 200 chars of local_llm response>
---
```

---

## Step 5: Post-Session Review

After all tasks in the plan are complete:

1. Check `~/.pedalpoint/fallback-log.md` for entries added in this session
2. Count entries since session start
3. If count > 0:
   > "N tasks ran on local LLM during fallback. Run Claude review pass now? (y/n)"
4. If user says yes: spawn Agent with prompt:
   > "Review the work done by local LLM during fallback. Check `~/.pedalpoint/fallback-log.md` for the task list, then run `git log --oneline -<N>` and `git diff HEAD~<N>` to see the changes. Identify any issues with code quality, correctness, or missed requirements and summarize your findings."
```

- [ ] **Step 3: Create skill scenario documents**

Create `tests/skill/scenarios/mechanical_routing.md`:

```markdown
# Scenario: Mechanical Task Routing

## Setup
- Project has `src/api/users.py` with a complete CRUD implementation
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Generate CRUD endpoints for the Post model (fields: title, body, author_id) following the existing User CRUD pattern"

## Expected Behavior
1. Skill classifies as mechanical (CRUD matching existing pattern)
2. Skill greps for existing CRUD: `grep -r "CRUD\|router\|get_db" src/ --include="*.py" -l`
3. Grep returns `src/api/users.py`
4. Skill reads 30-50 lines from users.py
5. Skill calls `local_llm` with augmented prompt containing the excerpt
6. Skill writes returned code to `src/api/posts.py`
7. Skill runs pytest, commits

## Verification
- `local_llm` tool was called (not Agent)
- Prompt included excerpt from users.py
- `src/api/posts.py` was created
- Commit exists on `feat/post-crud` branch
```

Create `tests/skill/scenarios/judgment_routing.md`:

```markdown
# Scenario: Judgment Task Routing

## Setup
- Fresh project, no existing patterns
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Design and implement the authentication system using JWT tokens"

## Expected Behavior
1. Skill classifies as judgment (security-sensitive, architectural decision)
2. Skill spawns Agent with full task context
3. Agent implements auth system

## Verification
- Agent was spawned (not local_llm)
- No local_llm call made
```

Create `tests/skill/scenarios/fallback_trigger.md`:

```markdown
# Scenario: Quota Exhaustion Fallback

## Setup
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid
- Task is a judgment task (Agent path)

## Input Task
"Refactor the database connection pooling logic"

## Simulated Event
Agent spawn fails with: "402 insufficient_quota: You have exceeded your monthly quota"

## Expected Behavior
1. Skill detects 402 error
2. Skill writes OPEN state to ~/.pedalpoint/state.json:
   - circuit: "open"
   - failure_count: 1
   - fallback_duration_minutes: 60
3. Skill re-routes task to local_llm via Context Courier (Step 3)
4. Task logged to ~/.pedalpoint/fallback-log.md
5. Subsequent tasks read OPEN state and skip to local_llm directly

## Verification
- ~/.pedalpoint/state.json exists with circuit: "open"
- ~/.pedalpoint/fallback-log.md has one entry
- local_llm was called for this task
```

Create `tests/skill/scenarios/probe_success.md`:

```markdown
# Scenario: HALF-OPEN Probe Succeeds

## Setup
- Circuit breaker: OPEN, expires timestamp is in the past
- PEDALPOINT_MODE: hybrid

## Expected Behavior
1. Skill reads state.json, sees OPEN + expired
2. Skill enters HALF-OPEN: spawns Agent with "Respond with only the word ok"
3. Agent succeeds
4. Skill writes {"circuit":"closed"} to state.json
5. Skill classifies and routes task normally (hybrid routing resumes)

## Verification
- ~/.pedalpoint/state.json contains {"circuit":"closed"} after probe
- Task routed via normal classification (not forced local_llm)
```

Create `tests/skill/scenarios/probe_failure.md`:

```markdown
# Scenario: HALF-OPEN Probe Fails (Doubles Backoff)

## Setup
- Circuit breaker: OPEN with failure_count: 1, fallback_duration_minutes: 60, expires in past
- PEDALPOINT_MODE: hybrid

## Simulated Event
Probe Agent spawn fails with: "402 quota exceeded"

## Expected Behavior
1. Skill reads state.json, sees OPEN + expired → HALF-OPEN
2. Probe Agent fails with 402
3. Skill writes updated OPEN state:
   - failure_count: 2
   - fallback_duration_minutes: 120
   - new expires: now + 120 minutes
4. Task routes to local_llm

## Verification
- ~/.pedalpoint/state.json has failure_count: 2
- ~/.pedalpoint/state.json has fallback_duration_minutes: 120
- local_llm called for the task
```

- [ ] **Step 4: Verify skill file is well-formed**

```bash
wc -l skills/route-tasks.md
head -5 skills/route-tasks.md
```

Expected: >100 lines, first line is `---` (frontmatter)

- [ ] **Step 5: Commit**

```bash
git add skills/ tests/skill/
git commit -m "feat: add companion skill route-tasks.md with routing logic, circuit breaker, Context Courier"
```

---

## Task 8: Install Script

**Branch:** `feat/install-script`

**Files:**
- Create: `install.sh`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b feat/install-script
```

- [ ] **Step 2: Create install.sh**

Create `install.sh`:

```sh
#!/usr/bin/env sh
set -e

# Defaults
PEDALPOINT_MODEL="${PEDALPOINT_MODEL:-gemma4:e4b}"
PEDALPOINT_BASE_URL="${PEDALPOINT_BASE_URL:-http://localhost:11434/v1}"
UNINSTALL=0

# Parse arguments
while [ "$#" -gt 0 ]; do
  case "$1" in
    --model)      PEDALPOINT_MODEL="$2";    shift 2 ;;
    --base-url)   PEDALPOINT_BASE_URL="$2"; shift 2 ;;
    --uninstall)  UNINSTALL=1;              shift   ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 1 ;;
  esac
done

SKILL_DIR="${HOME}/.claude/plugins/pedalpoint"
MCP_CONFIG="${HOME}/.claude/mcp.json"
STATE_DIR="${HOME}/.pedalpoint"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Uninstall ────────────────────────────────────────────────────────────────
if [ "$UNINSTALL" = "1" ]; then
  printf '→ Uninstalling pedalpoint...\n'

  # Remove MCP entry
  if [ -f "$MCP_CONFIG" ] && command -v jq >/dev/null 2>&1; then
    tmp=$(mktemp)
    jq 'del(.mcpServers.pedalpoint)' "$MCP_CONFIG" > "$tmp"
    mv "$tmp" "$MCP_CONFIG"
    printf '✓ Removed pedalpoint from %s\n' "$MCP_CONFIG"
  fi

  # Remove skill
  rm -rf "$SKILL_DIR"
  printf '✓ Removed skill directory %s\n' "$SKILL_DIR"

  # Uninstall package
  if command -v uv >/dev/null 2>&1; then
    uv tool uninstall pedalpoint 2>/dev/null || true
  elif command -v pipx >/dev/null 2>&1; then
    pipx uninstall pedalpoint 2>/dev/null || true
  else
    pip uninstall -y pedalpoint 2>/dev/null || true
  fi
  printf '✓ Package uninstalled\n'

  # Prompt before removing state
  printf '\nRemove ~/.pedalpoint/ (fallback logs and state)? [y/N] '
  read -r answer
  case "$answer" in
    [Yy]*) rm -rf "$STATE_DIR"; printf '✓ Removed %s\n' "$STATE_DIR" ;;
    *)     printf '→ Kept %s\n' "$STATE_DIR" ;;
  esac

  printf '\n✓ pedalpoint uninstalled. Restart Claude Code.\n'
  exit 0
fi

# ── Install ──────────────────────────────────────────────────────────────────

printf '→ Checking prerequisites...\n'

# Python 3.11+
if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 not found. Install Python 3.11+.\n' >&2; exit 1
fi
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
  printf 'ERROR: Python 3.11+ required.\n' >&2; exit 1
fi

# curl or git (needed for install itself)
if ! command -v curl >/dev/null 2>&1 && ! command -v git >/dev/null 2>&1; then
  printf 'ERROR: curl or git required.\n' >&2; exit 1
fi

# Ollama reachable (warn only)
OLLAMA_AVAILABLE=0
if curl -sf "${PEDALPOINT_BASE_URL}/models" >/dev/null 2>&1; then
  OLLAMA_AVAILABLE=1
else
  printf 'WARNING: Ollama not reachable at %s\n' "$PEDALPOINT_BASE_URL"
  printf '         Install Ollama or update PEDALPOINT_BASE_URL.\n'
fi

# ollama CLI (warn only)
OLLAMA_CLI=0
if command -v ollama >/dev/null 2>&1; then
  OLLAMA_CLI=1
else
  printf 'WARNING: ollama CLI not found — model pull will be skipped.\n'
fi

# ── Step 2: Detect package manager ──────────────────────────────────────────
if command -v uv >/dev/null 2>&1; then
  PKG_MGR="uv"
elif command -v pipx >/dev/null 2>&1; then
  PKG_MGR="pipx"
else
  PKG_MGR="pip"
fi

# ── Step 3: Install Python package ──────────────────────────────────────────
printf '→ Installing pedalpoint via %s...\n' "$PKG_MGR"
case "$PKG_MGR" in
  uv)   uv tool install pedalpoint ;;
  pipx) pipx install pedalpoint ;;
  pip)  pip install --user pedalpoint ;;
esac

# ── Step 4: Pull default model ───────────────────────────────────────────────
if [ "$OLLAMA_AVAILABLE" = "1" ] && [ "$OLLAMA_CLI" = "1" ]; then
  printf '→ Pulling model %s...\n' "$PEDALPOINT_MODEL"
  if ! ollama pull "$PEDALPOINT_MODEL"; then
    printf 'WARNING: Could not pull %s. Run manually: ollama pull %s\n' \
      "$PEDALPOINT_MODEL" "$PEDALPOINT_MODEL"
  fi
else
  printf 'WARNING: Skipping model pull. Run manually: ollama pull %s\n' "$PEDALPOINT_MODEL"
fi

# ── Step 6: Install companion skill ─────────────────────────────────────────
printf '→ Installing companion skill...\n'
mkdir -p "${SKILL_DIR}/skills"
cp "${SCRIPT_DIR}/skills/route-tasks.md" "${SKILL_DIR}/skills/"

# ── Step 7: Register MCP server ─────────────────────────────────────────────
printf '→ Registering MCP server in %s...\n' "$MCP_CONFIG"
ENTRY="{\"command\":\"pedalpoint-server\",\"args\":[],\"env\":{\"PEDALPOINT_BASE_URL\":\"${PEDALPOINT_BASE_URL}\",\"PEDALPOINT_MODEL\":\"${PEDALPOINT_MODEL}\",\"PEDALPOINT_MODE\":\"hybrid\",\"PEDALPOINT_TIMEOUT\":\"120\"}}"

if [ -f "$MCP_CONFIG" ] && command -v jq >/dev/null 2>&1; then
  tmp=$(mktemp)
  jq --argjson entry "$ENTRY" '.mcpServers.pedalpoint = $entry' "$MCP_CONFIG" > "$tmp"
  mv "$tmp" "$MCP_CONFIG"
elif [ ! -f "$MCP_CONFIG" ]; then
  mkdir -p "$(dirname "$MCP_CONFIG")"
  printf '{"mcpServers":{"pedalpoint":%s}}\n' "$ENTRY" > "$MCP_CONFIG"
else
  printf 'WARNING: jq not found — manually add pedalpoint to %s\n' "$MCP_CONFIG"
  printf 'Entry: {"mcpServers":{"pedalpoint":%s}}\n' "$ENTRY"
fi

# ── Step 8: Create state directory ──────────────────────────────────────────
mkdir -p "$STATE_DIR"

# ── Step 9: Summary ──────────────────────────────────────────────────────────
printf '\n'
printf '✓ pedalpoint installed!\n'
printf '✓ MCP server:  pedalpoint-server\n'
printf '✓ Skill:       pedalpoint:route-tasks\n'
printf '✓ Config:      %s\n' "$MCP_CONFIG"
printf '✓ State dir:   %s\n' "$STATE_DIR"
printf '\n'
printf '→ Restart Claude Code to activate.\n'
printf '→ Then invoke: pedalpoint:route-tasks\n'
```

- [ ] **Step 3: Make executable**

```bash
chmod +x install.sh
```

- [ ] **Step 4: Smoke test the script (dry run — do not actually install)**

```bash
bash -n install.sh && echo "syntax OK"
```

Expected: `syntax OK`

- [ ] **Step 5: Commit**

```bash
git add install.sh
git commit -m "feat: add install.sh with preflight checks, ollama pull, MCP config merge, uninstall"
```

---

## Task 9: GitHub Actions CI

**Branch:** `chore/ci`

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b chore/ci
```

- [ ] **Step 2: Create ci.yml**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: ["main", "feat/**", "fix/**", "chore/**", "test/**", "docs/**"]
  pull_request:
    branches: ["main"]

jobs:
  unit-tests:
    name: Unit Tests (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run unit tests with coverage
        run: |
          pytest tests/unit/ -v \
            --cov=pedalpoint \
            --cov-report=term-missing \
            --cov-fail-under=90

  integration-tests:
    name: Integration Tests (Ollama)
    runs-on: ubuntu-latest
    needs: unit-tests

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Ollama
        run: curl -fsSL https://ollama.ai/install.sh | sh

      - name: Start Ollama and pull model
        run: |
          ollama serve &
          sleep 5
          ollama pull gemma4:e4b

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run integration tests
        env:
          PEDALPOINT_INTEGRATION: "true"
          PEDALPOINT_MODEL: "gemma4:e4b"
        run: pytest tests/integration/ -v

  lint:
    name: Lint
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install ruff
        run: pip install ruff

      - name: Run ruff check
        run: ruff check src/ tests/

      - name: Run ruff format check
        run: ruff format --check src/ tests/
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "chore: add GitHub Actions CI (unit tests, integration tests, lint)"
```

---

## Task 10: README and CLAUDE.md

**Branch:** `docs/readme`

**Files:**
- Create: `README.md`
- Create: `CLAUDE.md`

- [ ] **Step 1: Create branch**

```bash
git checkout main
git checkout -b docs/readme
```

- [ ] **Step 2: Create README.md**

Create `README.md`:

```markdown
# pedalpoint

Route mechanical development tasks to a local LLM (Ollama, LM Studio, Jan) via Claude Code. Automatically falls back to local-only mode when Claude quota is exhausted.

## What it does

- **Hybrid routing:** Claude classifies each task. Mechanical work (scaffolding, CRUD, test stubs) goes to your local LLM. Judgment work (architecture, debugging, integration) stays with Claude.
- **Quota fallback:** When Claude returns a quota error, pedalpoint automatically switches to local-only mode and continues working. Switches back when quota restores.
- **Context Courier:** Before sending any task to the local LLM, pedalpoint greps your codebase for existing patterns and injects them into the prompt. Local LLMs only get tasks they have templates for.
- **Single install:** One script installs the MCP server, pulls the default model, and registers the companion skill.

## Requirements

- Claude Code
- Python 3.11+
- [Ollama](https://ollama.ai) (or any OpenAI-compatible inference server)

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | sh
```

With a custom model or endpoint:

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | \
  sh -s -- --model llama3 --base-url http://localhost:11434/v1
```

Restart Claude Code after install.

## Usage

Instead of `superpowers:subagent-driven-development`, invoke:

```
pedalpoint:route-tasks
```

pedalpoint handles routing automatically. No manual flagging needed.

## Modes

| Mode | Set via | Behavior |
|---|---|---|
| `hybrid` | default | Claude classifies each task |
| `local-only` | `PEDALPOINT_MODE=local-only` | All tasks → local LLM (use when quota exhausted preemptively) |
| `passthrough` | `PEDALPOINT_MODE=passthrough` | All tasks → Claude Agent (disables pedalpoint) |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PEDALPOINT_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint |
| `PEDALPOINT_MODEL` | `gemma4:e4b` | Default local model |
| `PEDALPOINT_MODE` | `hybrid` | Routing mode |
| `PEDALPOINT_TIMEOUT` | `120` | Read timeout in seconds |
| `PEDALPOINT_INITIAL_FALLBACK_MINUTES` | `60` | Initial circuit-open duration (doubles on each probe failure) |

## Uninstall

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | sh -s -- --uninstall
```

## Development

```sh
git clone https://github.com/EMSwank/pedalpoint
cd pedalpoint
pip install -e ".[dev]"
pytest tests/unit/ -v
```

Integration tests (requires Ollama running):

```sh
PEDALPOINT_INTEGRATION=true pytest tests/integration/ -v
```

## License

MIT
```

- [ ] **Step 3: Create CLAUDE.md**

Create `CLAUDE.md`:

```markdown
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
```

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: add README and CLAUDE.md developer guide"
```

---

## Task 11: Final Integration — Merge All Branches to Main

- [ ] **Step 1: Merge all feature branches**

Merge in order (each branch is independent; merge conflicts unlikely):

```bash
git checkout main
git merge feat/config         --no-ff -m "feat: config module"
git merge feat/error-classifier --no-ff -m "feat: error classifier"
git merge feat/circuit-breaker --no-ff -m "feat: circuit breaker utilities"
git merge feat/mcp-server     --no-ff -m "feat: MCP server"
git merge test/integration    --no-ff -m "test: integration scaffold"
git merge feat/companion-skill --no-ff -m "feat: companion skill"
git merge feat/install-script --no-ff -m "feat: install script"
git merge chore/ci            --no-ff -m "chore: GitHub Actions CI"
git merge docs/readme         --no-ff -m "docs: README and CLAUDE.md"
git merge chore/scaffolding   --no-ff -m "chore: scaffolding"
```

- [ ] **Step 2: Run full test suite on main**

```bash
pytest tests/unit/ -v --cov=pedalpoint --cov-report=term-missing --cov-fail-under=90
```

Expected: all unit tests pass, coverage ≥ 90%

- [ ] **Step 3: Verify entry point**

```bash
pedalpoint-server --help 2>&1 | head -3 || echo "entry point OK"
```

Expected: no ImportError

- [ ] **Step 4: Verify install script syntax**

```bash
bash -n install.sh && echo "install.sh syntax OK"
```

Expected: `install.sh syntax OK`

- [ ] **Step 5: Tag v0.1.0**

```bash
git tag -a v0.1.0 -m "pedalpoint v0.1.0 — initial release"
```
