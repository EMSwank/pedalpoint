# Scenario: Structural Path — Claude Patches Draft Inline (score 6)

## Setup
- Project has `src/api/users.py` with existing FastAPI routes
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a FastAPI route POST /posts that creates a post, following existing route patterns"

## Expected Behavior
1. Classified as structural (FastAPI route — framework-known)
2. Courier greps for `APIRouter`, finds users.py, picks a line range
3. `local_llm(task, target_path="src/api/posts.py", context_paths=["src/api/users.py:10-50"])`
4. Server writes `src/api/posts.py.draft`
5. Claude Reads the draft — one minor issue (missing `response_model=PostResponse`)
6. Claude fixes it with a single Edit on the `.draft`
7. `mv src/api/posts.py.draft src/api/posts.py`
8. pytest passes
9. `record_outcome(handoff_id, 6, "added response_model")`
10. Committed as `feat: add POST /posts route`

## Verification
- `.draft` file used (never written directly to posts.py)
- No review Agent spawned; the fix was a small inline Edit
- `record_outcome` score is 6 (fixed 1–3 lines)
- Final file is posts.py (no .draft suffix)
