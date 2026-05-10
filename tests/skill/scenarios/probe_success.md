# Scenario: HALF-OPEN Probe Succeeds

## Setup
- Circuit breaker: OPEN, expires timestamp is in the past
- PEDALPOINT_MODE: hybrid

## Expected Behavior
1. Skill reads state.json, sees OPEN + expired
2. Skill enters HALF-OPEN: spawns Agent with "Respond with only the word ok"
3. Agent succeeds
4. Skill writes {"circuit":"closed"} to state.json
5. Skill classifies and routes task normally (hybrid routing resumes)

## Verification
- ~/.pedalpoint/state.json contains {"circuit":"closed"} after probe
- Task routed via normal classification (not forced local_llm)
