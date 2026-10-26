# Scenario: Structural Path — Non-Trivial pytest Failure (Escalate)

## Setup
- Project has existing FastAPI routes with integration tests
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a Pydantic model PostCreate and wire it as the request body for POST /posts"

## Expected Behavior
1. Classified as structural (Pydantic model — framework-known)
2. `local_llm` writes the `.draft` with model and route code
3. Claude reviews inline, fixes a minor style issue with Edit
4. `mv` draft → target, pytest run
5. pytest fails: integration test fails because route handler references `PostCreate.content` but model defines `PostCreate.body`
6. Failure is non-trivial: logic error requiring understanding of test expectations
7. Skill escalates to judgment path
8. Agent spawned with full task + file path as context: "The local draft was promoted but pytest failed with a logic error: [paste failure]. See <target file>. Fix the implementation."
9. `record_outcome(handoff_id, 2, "logic error, escalated")`

## Verification
- Skill did NOT attempt inline fix (logic error, not trivial)
- Escalated to judgment with the promoted file path as context
- `record_outcome` score ≤ 2
- Agent handles the non-trivial fix
