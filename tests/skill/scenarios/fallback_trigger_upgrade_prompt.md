# Scenario: Quota Exhaustion Fallback — Claude Code Upgrade Prompt

## Setup
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid
- Task is a judgment task (Agent path)

## Input Task
"Refactor the database connection pooling logic"

## Simulated Event
Agent spawn fails with: "You've reached your usage limit. Upgrade your plan to continue."

## Expected Behavior
1. Skill matches `upgrade.*plan` or `usage.{0,20}limit` in the error text → classifies as hard quota
2. Skill writes api_fallback state to ~/.pedalpoint/state.json:
   - circuit: "api_fallback"
   - reason: "402_quota"
   - failure_count: 1
   - fallback_duration_minutes: 60
3. Skill re-routes task to claude_api
4. Subsequent tasks read api_fallback state and substitute claude_api for Agent

## Verification
- ~/.pedalpoint/state.json exists with circuit: "api_fallback"
- claude_api was called for this task (not local_llm)
- No entry in fallback-log.md (claude_api quality equivalent to Agent)

## Notes
Distinct from the HTTP 402 scenario (fallback_trigger.md): no numeric
status code in the error text. Tests that the upgrade-prompt pattern
matches without relying on "402", "quota", or "billing".
