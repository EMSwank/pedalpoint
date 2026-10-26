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
   - `BaseModel` (Pydantic) IS framework-known → proceeds with framework defaults note in `task`
3. Skill calls `local_llm(task=<spec details + note>, target_path="src/schemas/user.py", context_paths=[])`
4. Server writes `src/schemas/user.py.draft`; Claude Reads it and reviews inline
5. `mv` draft → `src/schemas/user.py`, pytest, `record_outcome`, commit

## Verification
- Classified as structural (not judgment)
- `task` carries the spec details; no pasted code
- `.draft` lifecycle used; no review Agent spawned
