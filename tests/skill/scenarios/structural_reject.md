# Scenario: Structural Path — Judgment Task in Disguise (score 1)

## Setup
- Project has existing route files
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a FastAPI route for user authentication that handles OAuth2 token exchange"

## Expected Behavior
1. Classified initially as structural (FastAPI route — framework-known)
2. Courier greps for route patterns, finds existing routes
3. `local_llm` writes `src/api/auth.py.draft` with basic route code
4. Claude Reads the draft and recognizes OAuth2 token exchange / credential handling — security-sensitive, needs judgment
5. `rm src/api/auth.py.draft`
6. `record_outcome(handoff_id, 1, "security-sensitive: judgment task")`
7. Task re-classified as judgment; judgment path runs

## Verification
- `.draft` deleted (not renamed)
- `record_outcome` score is 1
- Task escalated to judgment path
