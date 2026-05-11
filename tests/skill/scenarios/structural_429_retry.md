# Scenario: Structural Path — 429 Rate Limit During Agent Review

## Setup
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid
- Agent returns 429 on first review attempt, and again on retry

## Input Task
"Add a dataclass `Config` with fields: host (str), port (int), debug (bool = False)"

## Expected Behavior
1. Classified as structural (Python dataclass — framework-known)
2. local_llm drafts code, written to `src/config.py.draft`
3. Agent review spawn fails with 429
4. Skill waits 30 seconds
5. Retry: Agent review spawn fails with 429 again
6. Skill renames `src/config.py.draft` → `src/config.py` (use draft as-is)
7. Commit message flagged: `feat: add Config dataclass [unreviewed]`
8. Standard fallback log entry (NOT high priority):
   ```
   ## <ISO timestamp> — structural draft committed unreviewed (reason: 429_rate_limit)
   **Task:** Add a dataclass Config...
   **Draft preview:** <first 200 chars>
   ---
   ```
9. Circuit stays CLOSED (429 is not a quota error)

## Verification
- Waited 30s between attempts (one retry only)
- Commit message includes [unreviewed] flag
- Standard fallback log entry (no ⚠ HIGH PRIORITY)
- Circuit still CLOSED after task
