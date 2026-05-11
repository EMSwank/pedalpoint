# Scenario: Structural Path — Agent Patches Draft

## Setup
- Project has `src/api/users.py` with existing FastAPI routes
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a FastAPI route POST /posts that creates a post, following existing route patterns"

## Expected Behavior
1. Classified as structural (FastAPI route — framework-known)
2. Courier greps for `APIRouter`, finds users.py, extracts 40 lines
3. local_llm called with style excerpt, returns POST /posts handler code
4. Code written to `src/api/posts.py.draft`
5. Agent review spawned — draft has minor issue (missing response_model)
6. Agent outputs PATCH and adds `response_model=PostResponse` inline
7. Skill renames `src/api/posts.py.draft` → `src/api/posts.py`
8. pytest passes
9. Committed as `feat: add POST /posts route`

## Verification
- .draft file used (not written directly to posts.py)
- Agent review spawned before rename
- Agent output was PATCH (not REWRITE or REJECT)
- Final file is posts.py (no .draft suffix)
- pytest passed
