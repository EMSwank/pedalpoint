# Scenario: HALF-OPEN Probe Fails (Doubles Backoff)

## Setup
- Circuit breaker: OPEN with failure_count: 1, fallback_duration_minutes: 60, expires in past
- PEDALPOINT_MODE: hybrid

## Simulated Event
Probe Agent spawn fails with: "402 quota exceeded"

## Expected Behavior
1. Skill reads state.json, sees OPEN + expired → HALF-OPEN
2. Probe Agent fails with 402
3. Skill writes updated OPEN state:
   - failure_count: 2
   - fallback_duration_minutes: 120
   - new expires: now + 120 minutes
4. Task routes to local_llm

## Verification
- ~/.pedalpoint/state.json has failure_count: 2
- ~/.pedalpoint/state.json has fallback_duration_minutes: 120
- local_llm called for the task
