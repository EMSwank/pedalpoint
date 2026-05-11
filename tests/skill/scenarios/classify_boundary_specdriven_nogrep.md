# Scenario: Classification Boundary — Spec-Driven with Empty Grep, Not Framework-Known

## Setup
- No existing similar files in codebase
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid
- local_llm tool: available and responding

## Input Task
"Add a utility function `calculate_discount(price: float, tier: str) -> float` that applies tiered discounts: silver=5%, gold=10%, platinum=20%"

## Expected Routing
judgment (spec-driven, grep empty, NOT framework-known)

## Expected Behavior
1. Skill evaluates: is this framework-known? No — custom business logic, not a framework pattern
2. Is this spec-driven? Yes — types and behavior are specified
3. Context Courier runs: greps for `calculate_discount` or `discount` in project — empty
4. Task is spec-driven only (not framework-known) + grep empty → escalate to judgment
5. Skill spawns Agent with full task description
6. Agent implements the function

## Verification
- Classified as judgment (not structural)
- Agent spawned (not local_llm)
- No .draft file created
