# Scenario: Context Courier — Structural Task, Empty Grep, Spec-Driven Only

## Setup
- Empty project (no Python files matching patterns)
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a helper function `format_currency(amount: float, symbol: str = '$') -> str` that returns '$12.50' format"

## Expected Behavior
1. Evaluated: framework-known? No — custom utility, no framework owns this pattern
2. Evaluated: spec-driven? Yes — signature and behavior specified
3. Context Courier (structural): greps for `format_currency\|currency` — empty result
4. Task is spec-driven only (not framework-known) + grep empty → escalate to judgment
5. Agent spawned with full task description

## Verification
- Escalated to judgment (not structural execution)
- Agent spawned (not local_llm)
- No .draft file created
