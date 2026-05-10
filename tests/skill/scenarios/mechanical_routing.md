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
