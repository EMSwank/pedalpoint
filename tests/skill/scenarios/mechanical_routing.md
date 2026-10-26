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
3. Grep returns `src/api/users.py`; skill picks the relevant line range
4. Expected output is a new ~60-line file → skip rule does not apply
5. `local_llm(task, target_path="src/api/posts.py", context_paths=["src/api/users.py:1-60"])`
6. Claude Reads `src/api/posts.py.draft`, accepts it, `mv` → `src/api/posts.py`
7. pytest passes; `record_outcome(handoff_id, 7)`; commit

## Verification
- `local_llm` tool was called (not Agent) with a context path, not pasted code
- Claude never re-typed the generated code
- `src/api/posts.py` was created; commit exists on a feat branch
