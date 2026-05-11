# Scenario: Classify Structural — Framework-Known Pattern

## Setup
- No existing fixtures in the codebase (grep returns empty)
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid
- local_llm tool: available and responding

## Input Task
"Add a pytest fixture named `db_session` that creates a SQLAlchemy test session, yields it, and rolls back on teardown"

## Expected Routing
structural (framework-known: pytest fixture — framework provides the template)

## Expected Behavior
1. Skill classifies as structural (pytest fixture is a framework-known pattern)
2. Step 3 Context Courier runs for structural task:
   - Greps for `pytest.fixture` in project
   - Grep returns empty (no existing fixtures)
   - Task is framework-known → proceeds with "No existing project pattern found. Follow framework defaults." note
3. Skill calls local_llm with augmented prompt including framework note
4. Skill writes returned code to `tests/conftest.py.draft`
5. Skill spawns Agent review with PATCH/REWRITE/REJECT prompt
6. Agent responds PATCH or REWRITE
7. Skill renames `tests/conftest.py.draft` → `tests/conftest.py`
8. Skill runs pytest, commits

## Verification
- local_llm was called (not Agent for initial generation)
- Output written to `tests/conftest.py.draft` before Agent review
- Agent review was spawned
- Final file is `tests/conftest.py` (no `.draft` suffix)
- Commit exists on feat branch
