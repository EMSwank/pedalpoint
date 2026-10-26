# Scenario: Draft Error — Mistyped Context Path Is Not a Circuit Event

## Setup
- Circuit breaker: api_fallback (not expired)
- PEDALPOINT_MODE: hybrid

## Input Task
Judgment task routed to `claude_api` with `context_paths=["src/htpp/client.py:1-40"]` (typo)

## Expected Behavior
1. `claude_api` returns `Cannot read 'src/htpp/client.py': [Errno 2] No such file or directory…`
2. Skill matches the draft-errors table first (`Cannot read`) — NOT the `claude_api` catch-all
3. Skill fixes the path to `src/http/client.py:1-40` and retries once
4. state.json unchanged

## Verification
- Circuit stays `api_fallback` (no OPEN state written)
- No fallback-log entry
