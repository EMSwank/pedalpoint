# Scenario: Structural Path — Circuit Already OPEN at Task Start

## Setup
- Circuit breaker: OPEN (expires in 30 minutes)
- ~/.pedalpoint/state.json exists with circuit: "open"
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a pytest fixture `mock_db` that returns a MagicMock database session"

## Expected Behavior
1. Step 1: reads state.json — circuit is OPEN, expires in future
2. Step 1 routes: skip to Step 4 (local_llm, no classification)
3. Step 2 classification is skipped — task is NOT classified as structural
4. Context Courier runs in mechanical mode (grep for pattern)
5. local_llm called, code written directly to target file (no .draft)
6. pytest run, committed
7. Note: since task was never classified as structural, no HIGH PRIORITY log entry

## Verification
- Step 2 was skipped (no structural/mechanical classification ran)
- No .draft file used (went directly to target file)
- No Agent review spawned
- Task completed via mechanical fallback path
