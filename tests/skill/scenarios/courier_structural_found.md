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
4. Skill reads 30-50 lines from users.py showing route structure and error handling
5. Augmented prompt includes the users.py excerpt as style reference
6. local_llm called with style context
7. Output written to `src/api/posts.py.draft`
8. Agent review spawned

## Verification
- Courier grep ran for style conventions (not implementation pattern)
- Prompt included excerpt from users.py
- Prompt did NOT include "No existing project pattern found" note
