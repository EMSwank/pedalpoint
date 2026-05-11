# Scenario: Structural Path — Agent Rejects Draft (Judgment Task in Disguise)

## Setup
- Project has existing route files
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a FastAPI route for user authentication that handles OAuth2 token exchange"

## Expected Behavior
1. Classified initially as structural (FastAPI route — framework-known)
2. Courier greps for route patterns, finds existing routes
3. local_llm returns basic route code
4. Code written to `src/api/auth.py.draft`
5. Agent review spawned
6. Agent outputs REJECT: "This task involves OAuth2 token exchange and credential handling — security-sensitive logic requiring judgment routing."
7. Skill deletes `src/api/auth.py.draft`
8. Task re-classified as judgment
9. Agent spawned with full task description and security context

## Verification
- Agent review output was REJECT with reason
- .draft file was deleted (not renamed)
- Task escalated to judgment path
- Final Agent handles the auth implementation
