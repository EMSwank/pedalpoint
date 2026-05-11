# Scenario: Structural Path — 402 Quota Error During Agent Review

## Setup
- Circuit breaker: CLOSED at task start
- PEDALPOINT_MODE: hybrid
- local_llm: available

## Input Task
"Add a Pydantic model OrderCreate with fields: items (list[str]), total (float)"

## Expected Behavior
1. Classified as structural (Pydantic model)
2. Courier runs, local_llm drafts code
3. Code written to `src/schemas/order.py.draft`
4. Agent review spawn fails with 402 quota error
5. Skill writes OPEN circuit state to `~/.pedalpoint/state.json`:
   ```json
   {
     "circuit": "open",
     "reason": "402_quota",
     "opened_at": "<current UTC ISO>",
     "expires": "<current UTC + 60 min ISO>",
     "failure_count": 1,
     "fallback_duration_minutes": 60,
     "tasks_rerouted": 0
   }
   ```
6. Skill renames `src/schemas/order.py.draft` → `src/schemas/order.py` (uses draft content as-is, does NOT re-run local_llm)
7. Skill appends HIGH PRIORITY entry to `~/.pedalpoint/fallback-log.md`:
   ```
   ## <ISO timestamp> — structural draft committed unreviewed (reason: 402_quota) ⚠ HIGH PRIORITY
   **Task:** Add a Pydantic model OrderCreate...
   **Risk:** Agent review skipped due to quota. Logic correctness unverified.
   **Draft preview:** <first 200 chars of draft>
   ---
   ```
8. Commits with conventional format

## Verification
- Circuit opened (state.json written)
- .draft renamed to real file (not deleted, not re-run)
- HIGH PRIORITY entry in fallback-log.md
- Subsequent tasks will see OPEN circuit and skip to mechanical path
