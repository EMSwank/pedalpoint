# Scenario: HALF-OPEN Probe Fails — Unrecognized Error (Catch-All)

## Setup
- Circuit breaker: OPEN with failure_count: 1, fallback_duration_minutes: 60, expires in past
- PEDALPOINT_MODE: hybrid

## Simulated Event
Probe Agent spawn fails with: "Service temporarily unavailable. Please try again later."
(Does not contain 402, quota, billing, rate limit, or any known pattern.)

## Expected Behavior
1. Skill reads state.json, sees OPEN + expired → HALF-OPEN
2. Probe Agent fails with unrecognized error text
3. Catch-all branch fires: treat as hard quota
4. Skill writes updated OPEN state:
   - failure_count: 2
   - fallback_duration_minutes: 120
   - new expires: now + 120 minutes
5. Skill logs ⚠ HIGH PRIORITY entry with full error text
6. Task routes to local_llm

## Verification
- ~/.pedalpoint/state.json has failure_count: 2
- ~/.pedalpoint/state.json has fallback_duration_minutes: 120
- fallback-log.md has ⚠ HIGH PRIORITY entry containing the unrecognized error text
- local_llm called for the task

## Notes
Tests the Step 1b catch-all added to prevent silent execution stop on
novel error text (e.g. new Claude Code UI messages, infrastructure
errors that don't match any known pattern).
