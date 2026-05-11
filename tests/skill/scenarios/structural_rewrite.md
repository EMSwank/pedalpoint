# Scenario: Structural Path — Agent Rewrites Draft

## Setup
- Project has `src/api/users.py` with existing FastAPI routes using dependency injection
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a FastAPI route GET /posts that returns a paginated list of posts"

## Expected Behavior
1. Classified as structural (FastAPI route — framework-known)
2. Courier greps for `APIRouter`, finds users.py, extracts style excerpt
3. local_llm returns route code that ignores existing dependency injection pattern
4. Code written to `src/api/posts.py.draft`
5. Agent review spawned — draft is significantly wrong (missing db dependency, wrong return type)
6. Agent outputs REWRITE and produces corrected version using project's dependency pattern
7. Agent's rewrite overwrites `src/api/posts.py.draft`
8. Skill renames draft → `src/api/posts.py`
9. pytest passes, committed

## Verification
- Agent output was REWRITE
- .draft was overwritten before rename
- Final committed code uses project's dependency injection pattern
