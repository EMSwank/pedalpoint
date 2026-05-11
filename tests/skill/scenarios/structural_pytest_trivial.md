# Scenario: Structural Path — Trivial pytest Failure (Fix Inline)

## Setup
- Project has existing Pydantic models
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a Pydantic model UserUpdate with fields: name (str, optional), email (EmailStr, optional)"

## Expected Behavior
1. Classified as structural (Pydantic model — framework-known)
2. Courier finds existing model file, extracts style
3. local_llm returns model code missing `from typing import Optional` import
4. Code written to `src/schemas/user_update.py.draft`
5. Agent reviews, outputs PATCH (adds Optional import inline)
6. Draft renamed to `src/schemas/user_update.py`
7. pytest fails: `NameError: name 'Optional' not found`
8. Skill inspects failure: single missing import — `Optional` IS used elsewhere in the file (in another field)
9. Trivial fix: add `from typing import Optional` to imports, re-run pytest once
10. pytest passes, committed

## Trivial definition (for reference)
Trivial = single-line syntax error, missing import already present elsewhere in the file,
or typo in variable/function name. This scenario qualifies because Optional is in the same file.

## Verification
- Skill fixed inline without escalating
- Only one re-run of pytest
- Committed successfully
