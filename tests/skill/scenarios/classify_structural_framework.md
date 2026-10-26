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
   - Task is framework-known → `task` text includes "No existing project pattern found. Follow framework defaults for pytest."
3. Expected change is > 30 lines or a new file of fixture boilerplate → skip rule does not apply
4. Skill calls `local_llm(task=..., target_path="tests/conftest.py", context_paths=[])`
5. Server writes `tests/conftest.py.draft`; skill Reads the draft
6. Draft is correct → `mv tests/conftest.py.draft tests/conftest.py`
7. Skill runs pytest → passes
8. `record_outcome(handoff_id, 7)`; commit

## Verification
- local_llm was called with `target_path`, not with pasted code
- No review Agent was spawned; Claude reviewed the draft inline
- Final file is `tests/conftest.py` (no `.draft` suffix)
- `record_outcome` called with the handoff_id from the local_llm result
