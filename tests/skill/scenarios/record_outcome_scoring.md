# Scenario: record_outcome Scoring

For each handoff in a CLOSED or api_fallback circuit, after the draft is promoted
(or abandoned), the skill calls `record_outcome(handoff_id, score, note)` with:

| What Claude did | Expected score |
|---|---|
| Accepted draft unchanged | 7 |
| Fixed a missing import | 6 |
| Fixed 5 lines across the file | 5 |
| Rewrote one function of three | 4 |
| Rewrote most of the file | 3 |
| Started over, kept the draft's structure | 2 |
| Deleted the draft (judgment in disguise) | 1 |

## Verification
- Exactly one `record_outcome` per handoff, using the `handoff_id` from the tool result
- Score reflects edits Claude made (including trivial pytest fixes), not code style
- Empty-output retry: the failed attempt has no handoff_id, so no outcome is recorded for it
