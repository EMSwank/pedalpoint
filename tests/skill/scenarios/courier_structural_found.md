# Scenario: Context Courier — Structural Task, Style Conventions Found

## Setup
- Project has `src/api/users.py` with FastAPI routes using `HTTPException` and a `UserResponse` model
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a FastAPI route GET /posts/{post_id} that returns a Post or raises 404"

## Expected Behavior
1. Classified as structural (FastAPI route — framework-known)
2. Context Courier (structural): greps for `APIRouter\|HTTPException` in project
3. Grep returns `src/api/users.py`
4. Skill locates the 30–50 lines showing route structure and error handling (e.g. `grep -n` or Read) to pick a line range
5. `local_llm` called with `context_paths=["src/api/users.py:12-55"]` and `target_path="src/api/posts.py"`
6. Server writes `src/api/posts.py.draft`; Claude reviews inline

## Verification
- Courier grep ran for style conventions (not implementation pattern)
- users.py passed as a `path:START-END` context spec — excerpt NOT pasted into `task`
- `task` did NOT include "No existing project pattern found" note
