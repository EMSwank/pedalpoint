# Junior/Senior Routing Model — Design Spec

**Date:** 2026-05-11
**Status:** Approved
**Scope:** Redesign `skills/route-tasks/SKILL.md` to implement three-tier routing with a supervised draft path.

---

## Overview

Extend the route-tasks skill from two tiers (mechanical/judgment) to three tiers by adding a **structural** tier. The structural tier lets the local LLM draft output for greenfield and framework-standard tasks, with Agent acting as senior reviewer before commit.

Mental model: local LLM = junior dev, Agent = senior dev. Junior implements. Senior reviews, patches, or rewrites. Senior always has final say before code lands.

---

## Tier Definitions

| Tier | Route | Courier | Review |
|---|---|---|---|
| mechanical | local_llm direct | implementation pattern (grep required) | none — pytest verifies |
| structural | local_llm draft + Agent review | style conventions (grep, fallback to framework defaults) | Agent patches, rewrites, or rejects |
| judgment | Agent only | — | N/A |

### Mechanical — unchanged

Route when ALL apply:
- Generates code matching an established pattern already in the codebase
- Pattern verified by grep
- No architectural decision required
- No cross-system integration
- No security-sensitive logic

### Structural — new

Route when ANY apply:
- Task involves a **framework-known pattern**: pytest fixture/test, FastAPI route/router, Pydantic model, dataclass, Alembic migration stub, docstring block, README section
- Task is **spec-driven**: field names, types, and behavior fully spelled out in the task description — no ambiguity, no open questions

### Judgment — unchanged

Route when ANY apply:
- Architecture or design decision required
- Debugging with unknown root cause
- Cross-system integration
- Security-sensitive logic (auth, payments, tokens, credentials)
- Ambiguous requirements
- Novel logic with no codebase or framework template

**When in doubt: route to judgment.**

---

## Context Courier — Extended

Runs for both mechanical and structural tasks. Different grep target per tier.

**Mechanical courier** (unchanged):
- Grep for implementation pattern
- Empty result → escalate to judgment (do not call local_llm)

**Structural courier** (new):
- Grep for style conventions: existing Response models, exception handling patterns, similar route/model/fixture files
- Empty result → proceed anyway. Inject note: "No existing project pattern found. Follow framework defaults."
- Framework-known tasks always proceed regardless of grep result (framework itself is the template)
- Spec-driven tasks with empty grep AND no framework-known pattern → escalate to judgment

Courier prompt structure (both tiers):
```
system: "You are a code generator. Follow the provided patterns exactly. Output only code. No explanation."

prompt: |
  ## Existing pattern (<filepath> lines <N>-<M>):
  <excerpt — 30–50 lines>

  ## Task:
  <task description>
  Follow the exact naming conventions, structure, and patterns shown above.
```

---

## Structural Path — Step by Step

1. Run Context Courier (grep for style conventions)
2. Call `local_llm` with courier-augmented prompt
3. Write output to `<target_file>.draft` (NOT the real filename)
4. Spawn Agent review:
   ```
   Review <target>.draft against the task description below.
   - If structurally sound with only minor issues: patch the draft inline and output PATCH.
   - If significantly wrong but salvageable: rewrite the draft and output REWRITE.
   - If this is a judgment task in disguise or cannot be fixed mechanically: output REJECT and reason.
   Task: <task description>
   ```
5. Agent result:
   - `PATCH` → Agent has edited `.draft` inline; proceed
   - `REWRITE` → Agent has overwritten `.draft`; proceed
   - `REJECT` → delete `.draft`, re-classify as judgment, run judgment path
6. Rename `.draft` → `<target_file>`
7. Run `pytest -x -q`
8. On test failure:
   - **Trivial** (fix inline): single-line syntax error, missing import already present elsewhere in the file, typo in variable/function name → fix and re-run
   - **Non-trivial** (escalate): logic error, multiple file changes needed, new dependency required → escalate to judgment path
9. Commit (Conventional Commits format)

---

## Error Handling

### Agent review failures (structural path)

| Error | Action |
|---|---|
| `402/quota/billing/insufficient` | Open circuit. Rename `.draft` → target_file (use draft content as-is; do not re-run local_llm). Log HIGH PRIORITY entry to fallback-log. |
| `429/rate-limit` | Wait 30s, retry review once. Still failing → commit `.draft` as-is, flag commit message `[unreviewed]`, log standard fallback entry. |
| `529/overload/capacity` | Same as 429 fallback. |
| `timeout/connection` | Delete `.draft`. Re-classify as judgment. Run judgment path. |
| Agent returns `REJECT` | Delete `.draft`. Re-classify as judgment. Run judgment path. |

### Circuit OPEN — structural behavior

Skip Agent review. Write local_llm output directly to target file (no `.draft`). Log HIGH PRIORITY entry to fallback-log.

### `local-only` mode — structural behavior

Skip Agent review. Write local_llm output directly to target file (no `.draft`). No fallback log entry (local-only is intentional, not a fallback).

### pytest non-trivial failure (structural path)

Delete renamed file. Re-classify as judgment. Pass local_llm draft content as context to Agent spawn.

---

## Fallback Log Entries

**Standard structural fallback** (429/529):
```markdown
## <ISO timestamp> — structural draft committed unreviewed (reason: <reason>)
**Task:** <task description>
**Draft preview:** <first 200 chars of local_llm response>
---
```

**High-priority structural fallback** (402 quota or circuit OPEN):
```markdown
## <ISO timestamp> — structural draft committed unreviewed (reason: <reason>) ⚠ HIGH PRIORITY
**Task:** <task description>
**Risk:** Agent review skipped due to quota. Logic correctness unverified.
**Draft preview:** <first 200 chars of local_llm response>
---
```

### Post-session review prompt (updated)

> "N tasks ran on local LLM during fallback. M structural drafts committed unreviewed — K marked HIGH PRIORITY (quota fallback). Review HIGH PRIORITY items first. Run Claude review pass now? (y/n)"

---

## Testing

Skill has no Python backing. Tests are manual scenarios in `tests/skill/scenarios/`.

### New scenarios required

**Classification:**
- `classify_structural_framework.md` — "add pytest fixture" with no existing fixture → structural
- `classify_structural_specdriven.md` — fully specified task (field names, types, behavior) → structural
- `classify_boundary_specdriven_nogrep.md` — spec-driven, empty grep, not framework-known → judgment

**Structural path:**
- `structural_patch.md` — Agent patches draft → renamed, committed
- `structural_rewrite.md` — Agent rewrites draft → overwritten, committed
- `structural_reject.md` — Agent returns REJECT → draft deleted, judgment path
- `structural_pytest_trivial.md` — pytest fails on missing import already in file → fixed inline
- `structural_pytest_nontrivial.md` — pytest fails on logic error → judgment escalation

**Error/fallback:**
- `structural_402_fallback.md` — 402 during review → circuit opens, HIGH PRIORITY log
- `structural_429_retry.md` — 429 during review → retry, then commit unreviewed
- `structural_circuit_open.md` — circuit OPEN at task start → skip review, HIGH PRIORITY log

**Context Courier:**
- `courier_structural_found.md` — grep finds style conventions → injected into prompt
- `courier_structural_empty_framework.md` — grep empty, framework-known → proceeds with fallback note
- `courier_structural_empty_specdriven.md` — grep empty, spec-driven only → judgment escalation

---

## Unchanged

- Prerequisites check (MCP tool probe, Ollama ping)
- Step 1: circuit breaker state read
- Mechanical path execution (local_llm → write → pytest → commit)
- Judgment path execution (Agent spawn + error handling)
- Step 4b error handling for Agent spawns
- `PEDALPOINT_MODE` env var behavior (`local-only`, `passthrough`, `hybrid`)
- State file format (`~/.pedalpoint/state.json`)
- Circuit breaker open/close/half-open logic
