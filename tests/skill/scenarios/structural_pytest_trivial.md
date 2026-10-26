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
4. Server writes `src/schemas/user_update.py.draft`
5. Claude Reads the draft and misses the absent import (review is a quick read)
6. `mv` draft → `src/schemas/user_update.py`
7. pytest fails: `NameError: name 'Optional' not found`
8. Skill inspects failure: single missing import — `Optional` appears multiple times in the file (name and email fields both use it), so the import is clearly needed
9. Trivial fix: add `from typing import Optional` to imports, re-run pytest once
10. pytest passes; `record_outcome(handoff_id, 6, "added Optional import")`; committed

## Trivial definition (for reference)
Trivial = single-line syntax error, missing import whose usage is already present in the file,
or typo in variable/function name. This scenario qualifies because Optional is used in multiple
fields in the same file — the needed import is unambiguous.

## Verification
- Skill fixed inline without escalating
- Only one re-run of pytest
- `record_outcome` score is 6
- Committed successfully
