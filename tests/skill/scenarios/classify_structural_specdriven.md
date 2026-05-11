# Scenario: Classify Structural — Spec-Driven Task

## Setup
- No existing Pydantic models in codebase (grep returns empty for BaseModel)
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid
- local_llm tool: available and responding

## Input Task
"Add a Pydantic model `UserCreate` with fields: name (str, required), email (EmailStr, required), age (int, optional, default None)"

## Expected Routing
structural (spec-driven: field names, types, and behavior fully spelled out)

## Expected Behavior
1. Skill classifies as structural (fully specified task — no open questions)
2. Step 3 Context Courier runs:
   - Greps for `BaseModel` in project
   - Grep returns empty
   - Task is spec-driven only (not framework-known) → checks: is grep empty AND not framework-known?
   - `BaseModel` (Pydantic) IS framework-known → proceeds with framework defaults note
3. Skill calls local_llm with augmented prompt
4. Writes to `src/schemas/user.py.draft`
5. Agent reviews draft
6. Renames, runs pytest, commits

## Verification
- Classified as structural (not judgment)
- local_llm called with spec details in prompt
- .draft lifecycle used
