# Scenario: Circuit Already OPEN at Task Start (unreviewed draft)

## Setup
- Circuit breaker: OPEN (expires in 30 minutes)
- ~/.pedalpoint/state.json exists with circuit: "open"
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a pytest fixture `mock_db` that returns a MagicMock database session"

## Expected Behavior
1. Step 1: reads state.json — circuit is OPEN, expires in future
2. Step 1 routes: skip to Step 3 courier (mechanical mode) then Step 4 open-circuit path
3. Step 2 classification is skipped; skip rule is OFF
4. `local_llm(task, target_path="tests/conftest.py", context_paths=[...])` writes the `.draft`
5. No review (Claude quota exhausted): `mv tests/conftest.py.draft tests/conftest.py`
6. pytest run; commit message flagged `[unreviewed]`
7. Entry appended to `~/.pedalpoint/fallback-log.md` ("task rerouted")
8. `record_outcome` is NOT called

## Verification
- Step 2 was skipped
- Draft promoted with `mv`, without inline review edits
- Commit message contains `[unreviewed]`
- fallback-log.md entry exists; no outcome record
