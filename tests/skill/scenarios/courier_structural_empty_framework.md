# Scenario: Context Courier — Structural Task, Empty Grep, Framework-Known

## Setup
- Empty project (no Python files matching patterns)
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a pytest fixture `client` that creates a FastAPI TestClient"

## Expected Behavior
1. Classified as structural (pytest fixture — framework-known)
2. Context Courier (structural): greps for `pytest.fixture` — empty result
3. Task is framework-known → proceed with fallback note
4. Augmented prompt includes: "No existing project pattern found. Follow framework defaults for pytest/FastAPI."
5. local_llm called
6. Output written to `tests/conftest.py.draft`
7. Agent review spawned

## Verification
- Courier grep ran and returned empty
- Skill did NOT escalate to judgment
- Prompt includes "No existing project pattern found" note
- .draft lifecycle used
