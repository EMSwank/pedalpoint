# Scenario: Draft Refused — Target Too Large / Context Too Large

## Setup
- `src/models.py` has 450 lines
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a `Tag` model to src/models.py following the existing model pattern"

## Expected Behavior
1. `local_llm(target_path="src/models.py", ...)` returns error containing `too large for local regeneration`
2. Not a circuit event
3. Claude does the task directly with Edit

## Variant
- Error contains `Context too large` → same handling (Claude does it directly)

## Verification
- state.json unchanged; no `.draft`; no `record_outcome`
