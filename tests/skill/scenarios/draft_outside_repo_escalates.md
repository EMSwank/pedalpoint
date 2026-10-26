# Scenario: Draft Refused — Path Outside the Project Repo

## Setup
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid
- Task's target lives in a sibling repo (`../shared-lib/utils.py`)

## Input Task
"Add a `slugify` helper to ../shared-lib/utils.py"

## Expected Behavior
1. `local_llm` returns error containing `outside the project repo`
2. Not a circuit event: state.json unchanged
3. Claude does the task directly

## Verification
- state.json unchanged; no fallback-log entry
- No `.draft` written anywhere
