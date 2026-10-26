# Scenario: Skip Rule — Tiny Change Done Directly

## Setup
- Project has `src/config.py` (80 lines)
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a `retries: int = 3` field to the Settings dataclass"

## Expected Behavior
1. Classified as mechanical
2. Expected lines changed ≈ 1 (< ~30) → skip rule applies
3. Claude makes the change directly with Edit
4. pytest, commit

## Verification
- `local_llm` NOT called; no `.draft` created; no `record_outcome`

## Variant: PEDALPOINT_MODE=local-only
- Skip rule is OFF → `local_llm` IS called even for this tiny change
