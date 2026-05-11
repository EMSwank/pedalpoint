# Scenario: Structural Path — Non-Trivial pytest Failure (Escalate)

## Setup
- Project has existing FastAPI routes with integration tests
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a Pydantic model PostCreate and wire it as the request body for POST /posts"

## Expected Behavior
1. Classified as structural (Pydantic model — framework-known)
2. local_llm returns model and route code
3. Agent reviews, outputs PATCH for minor style issue
4. Draft renamed, pytest run
5. pytest fails: integration test fails because route handler references `PostCreate.content` but model defines `PostCreate.body`
6. Failure is non-trivial: logic error requiring understanding of test expectations
7. Skill escalates to judgment path
8. Agent spawned with full task + draft content as context: "The structural draft was committed but pytest failed with a logic error: [paste failure]. Draft content: [paste code]. Fix the implementation."

## Verification
- Skill did NOT attempt inline fix (logic error, not trivial)
- Escalated to judgment with draft content passed as context
- Agent handles the non-trivial fix
