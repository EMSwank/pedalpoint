# Scenario: Structural Path — Claude Rewrites Most of the Draft (score 3)

## Setup
- Project has `src/api/users.py` with existing FastAPI routes using dependency injection
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a FastAPI route GET /posts that returns a paginated list of posts"

## Expected Behavior
1. Classified as structural (FastAPI route — framework-known)
2. Courier greps for `APIRouter`, finds users.py, passes a line range in `context_paths`
3. `local_llm` writes `src/api/posts.py.draft` that ignores the dependency injection pattern
4. Claude Reads the draft — significantly wrong (missing db dependency, wrong return type)
5. Claude rewrites most of the draft (Write/Edit on the `.draft`) using the project's dependency pattern
6. `mv` draft → `src/api/posts.py`; pytest passes
7. `record_outcome(handoff_id, 3, "rewrote handler: missing get_db dependency")`; commit

## Verification
- No review Agent spawned
- `record_outcome` score is 3 (rewrote most)
- Final committed code uses project's dependency injection pattern
