# Scenario: Judgment Task Routing

## Setup
- Fresh project, no existing patterns
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Design and implement the authentication system using JWT tokens"

## Expected Behavior
1. Skill classifies as judgment (security-sensitive, architectural decision)
2. Skill spawns Agent with full task context
3. Agent implements auth system

## Verification
- Agent was spawned (not local_llm)
- No local_llm call made
