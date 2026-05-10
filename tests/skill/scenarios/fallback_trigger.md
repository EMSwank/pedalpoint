# Scenario: Quota Exhaustion Fallback

## Setup
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid
- Task is a judgment task (Agent path)

## Input Task
"Refactor the database connection pooling logic"

## Simulated Event
Agent spawn fails with: "402 insufficient_quota: You have exceeded your monthly quota"

## Expected Behavior
1. Skill detects 402 error
2. Skill writes OPEN state to ~/.pedalpoint/state.json:
   - circuit: "open"
   - failure_count: 1
   - fallback_duration_minutes: 60
3. Skill re-routes task to local_llm via Context Courier (Step 3)
4. Task logged to ~/.pedalpoint/fallback-log.md
5. Subsequent tasks read OPEN state and skip to local_llm directly

## Verification
- ~/.pedalpoint/state.json exists with circuit: "open"
- ~/.pedalpoint/fallback-log.md has one entry
- local_llm was called for this task
