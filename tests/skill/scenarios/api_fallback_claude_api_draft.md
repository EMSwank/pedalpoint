# Scenario: api_fallback — claude_api Writes the Draft for a Judgment Task

## Setup
- Circuit breaker: api_fallback (not expired)
- ANTHROPIC_API_KEY set
- PEDALPOINT_MODE: hybrid

## Input Task
"Implement exponential backoff with jitter for the HTTP client's retry policy in src/http/retry.py"

## Expected Behavior
1. Classified as judgment (novel logic); API mode active → `claude_api` instead of Agent
2. `claude_api(task, target_path="src/http/retry.py", context_paths=["src/http/client.py:1-40"])`
3. Server writes `src/http/retry.py.draft`; result JSON has `"backend": "claude_api"`
4. Claude reviews inline, `mv`, pytest, `record_outcome`, commit

## Variant
- A structural task in api_fallback still uses `local_llm` (local path unchanged)

## Verification
- `claude_api` called with `target_path` (same contract as local_llm)
- Claude never re-typed the returned code
- `record_outcome` called with the claude_api handoff_id
