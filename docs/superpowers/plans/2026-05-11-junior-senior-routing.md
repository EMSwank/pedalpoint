# Junior/Senior Routing Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `skills/route-tasks/SKILL.md` from two-tier routing (mechanical/judgment) to three-tier routing, adding a supervised "structural" path where the local LLM drafts output and Agent reviews before commit.

**Architecture:** Single file is the implementation target: `skills/route-tasks/SKILL.md`. New structural tier sits between mechanical and judgment. Context Courier extended to grep for style conventions for structural tasks. Agent review uses `.draft` file naming to isolate unreviewed output. Error handling table extended for review-stage failures with HIGH PRIORITY logging for quota-triggered skips.

**Tech Stack:** Markdown (SKILL.md), Markdown (scenario files in `tests/skill/scenarios/`)

---

## File Map

| Action | Path |
|---|---|
| Modify | `skills/route-tasks/SKILL.md` |
| Create | `tests/skill/scenarios/classify_structural_framework.md` |
| Create | `tests/skill/scenarios/classify_structural_specdriven.md` |
| Create | `tests/skill/scenarios/classify_boundary_specdriven_nogrep.md` |
| Create | `tests/skill/scenarios/courier_structural_found.md` |
| Create | `tests/skill/scenarios/courier_structural_empty_framework.md` |
| Create | `tests/skill/scenarios/courier_structural_empty_specdriven.md` |
| Create | `tests/skill/scenarios/structural_patch.md` |
| Create | `tests/skill/scenarios/structural_rewrite.md` |
| Create | `tests/skill/scenarios/structural_reject.md` |
| Create | `tests/skill/scenarios/structural_pytest_trivial.md` |
| Create | `tests/skill/scenarios/structural_pytest_nontrivial.md` |
| Create | `tests/skill/scenarios/structural_402_fallback.md` |
| Create | `tests/skill/scenarios/structural_429_retry.md` |
| Create | `tests/skill/scenarios/structural_circuit_open.md` |
| Modify | `README.md` |
| Modify | `CLAUDE.md` |

---

### Task 1: Branch setup and classification scenario files

**Files:**
- Create branch: `feat/junior-senior-routing`
- Create: `tests/skill/scenarios/classify_structural_framework.md`
- Create: `tests/skill/scenarios/classify_structural_specdriven.md`
- Create: `tests/skill/scenarios/classify_boundary_specdriven_nogrep.md`

- [ ] **Step 1: Create feature branch**

```bash
git checkout main && git pull && git checkout -b feat/junior-senior-routing
```

- [ ] **Step 2: Write classify_structural_framework.md**

Create `tests/skill/scenarios/classify_structural_framework.md`:

```markdown
# Scenario: Classify Structural — Framework-Known Pattern

## Setup
- No existing fixtures in the codebase (grep returns empty)
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid
- local_llm tool: available and responding

## Input Task
"Add a pytest fixture named `db_session` that creates a SQLAlchemy test session, yields it, and rolls back on teardown"

## Expected Routing
structural (framework-known: pytest fixture — framework provides the template)

## Expected Behavior
1. Skill classifies as structural (pytest fixture is a framework-known pattern)
2. Step 3 Context Courier runs for structural task:
   - Greps for `pytest.fixture` in project
   - Grep returns empty (no existing fixtures)
   - Task is framework-known → proceeds with "No existing project pattern found. Follow framework defaults." note
3. Skill calls local_llm with augmented prompt including framework note
4. Skill writes returned code to `tests/conftest.py.draft`
5. Skill spawns Agent review with PATCH/REWRITE/REJECT prompt
6. Agent responds PATCH or REWRITE
7. Skill renames `tests/conftest.py.draft` → `tests/conftest.py`
8. Skill runs pytest, commits

## Verification
- local_llm was called (not Agent for initial generation)
- Output written to `tests/conftest.py.draft` before Agent review
- Agent review was spawned
- Final file is `tests/conftest.py` (no `.draft` suffix)
- Commit exists on feat branch
```

- [ ] **Step 3: Write classify_structural_specdriven.md**

Create `tests/skill/scenarios/classify_structural_specdriven.md`:

```markdown
# Scenario: Classify Structural — Spec-Driven Task

## Setup
- No existing Pydantic models in codebase (grep returns empty for BaseModel)
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid
- local_llm tool: available and responding

## Input Task
"Add a Pydantic model `UserCreate` with fields: name (str, required), email (EmailStr, required), age (int, optional, default None)"

## Expected Routing
structural (spec-driven: field names, types, and behavior fully spelled out)

## Expected Behavior
1. Skill classifies as structural (fully specified task — no open questions)
2. Step 3 Context Courier runs:
   - Greps for `BaseModel` in project
   - Grep returns empty
   - Task is spec-driven only (not framework-known) → checks: is grep empty AND not framework-known?
   - `BaseModel` (Pydantic) IS framework-known → proceeds with framework defaults note
3. Skill calls local_llm with augmented prompt
4. Writes to `src/schemas/user.py.draft`
5. Agent reviews draft
6. Renames, runs pytest, commits

## Verification
- Classified as structural (not judgment)
- local_llm called with spec details in prompt
- .draft lifecycle used
```

- [ ] **Step 4: Write classify_boundary_specdriven_nogrep.md**

Create `tests/skill/scenarios/classify_boundary_specdriven_nogrep.md`:

```markdown
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
```

- [ ] **Step 5: Commit scenario files**

```bash
git add tests/skill/scenarios/classify_structural_framework.md \
        tests/skill/scenarios/classify_structural_specdriven.md \
        tests/skill/scenarios/classify_boundary_specdriven_nogrep.md
git commit -m "test: add classification scenarios for structural tier"
```

---

### Task 2: Update Step 2 — add structural tier to classification

**Files:**
- Modify: `skills/route-tasks/SKILL.md` (Step 2 section)

- [ ] **Step 1: Replace Step 2 judgment section**

In `skills/route-tasks/SKILL.md`, find and replace:

Old:
```
### Route to Agent (judgment) when ANY applies:
- Architecture or design decision required
- Debugging with unknown root cause
- Cross-system integration
- Security-sensitive code
- Novel logic — no existing codebase pattern
- Requires reading multiple files to understand what to build

**When in doubt: route to Agent.**
```

New:
```
### Route to `local_llm` draft + Agent review (structural) when ANY apply:
- Task involves a framework-known pattern:
  - pytest fixture or test function
  - FastAPI route, router, or dependency injection
  - Pydantic model or schema
  - Python dataclass
  - Alembic migration stub
  - Docstring block
  - README section or documentation file
- Task is spec-driven: field names, types, and behavior are fully spelled out in the task description — no open questions, no ambiguity

**Examples:** "Add a pytest fixture that creates a test database session", "Add a Pydantic model for UserCreate with fields: name (str), email (EmailStr), age (int, optional)", "Write a README section explaining the circuit breaker behavior."

### Route to Agent (judgment) when ANY applies:
- Architecture or design decision required
- Debugging with unknown root cause
- Cross-system integration
- Security-sensitive code (auth, payments, tokens, credentials)
- Novel logic — no codebase pattern and no applicable framework standard
- Ambiguous requirements — open questions that need clarification before implementing
- Requires reading multiple files to understand what to build

**When in doubt: route to Agent.**
```

- [ ] **Step 2: Verify the edit looks correct**

```bash
grep -n "structural\|framework-known\|spec-driven" skills/route-tasks/SKILL.md
```

Expected: lines in Step 2 showing the new structural tier definition.

- [ ] **Step 3: Commit**

```bash
git add skills/route-tasks/SKILL.md
git commit -m "feat: add structural tier to Step 2 classification"
```

---

### Task 3: Context Courier scenario files

**Files:**
- Create: `tests/skill/scenarios/courier_structural_found.md`
- Create: `tests/skill/scenarios/courier_structural_empty_framework.md`
- Create: `tests/skill/scenarios/courier_structural_empty_specdriven.md`

- [ ] **Step 1: Write courier_structural_found.md**

Create `tests/skill/scenarios/courier_structural_found.md`:

```markdown
# Scenario: Context Courier — Structural Task, Style Conventions Found

## Setup
- Project has `src/api/users.py` with FastAPI routes using `HTTPException` and a `UserResponse` model
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a FastAPI route GET /posts/{post_id} that returns a Post or raises 404"

## Expected Behavior
1. Classified as structural (FastAPI route — framework-known)
2. Context Courier (structural): greps for `APIRouter\|HTTPException` in project
3. Grep returns `src/api/users.py`
4. Skill reads 30-50 lines from users.py showing route structure and error handling
5. Augmented prompt includes the users.py excerpt as style reference
6. local_llm called with style context
7. Output written to `src/api/posts.py.draft`
8. Agent review spawned

## Verification
- Courier grep ran for style conventions (not implementation pattern)
- Prompt included excerpt from users.py
- Prompt did NOT include "No existing project pattern found" note
```

- [ ] **Step 2: Write courier_structural_empty_framework.md**

Create `tests/skill/scenarios/courier_structural_empty_framework.md`:

```markdown
# Scenario: Context Courier — Structural Task, Empty Grep, Framework-Known

## Setup
- Empty project (no Python files matching patterns)
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a pytest fixture `client` that creates a FastAPI TestClient"

## Expected Behavior
1. Classified as structural (pytest fixture — framework-known)
2. Context Courier (structural): greps for `pytest.fixture` — empty result
3. Task is framework-known → proceed with fallback note
4. Augmented prompt includes: "No existing project pattern found. Follow framework defaults for pytest/FastAPI."
5. local_llm called
6. Output written to `tests/conftest.py.draft`
7. Agent review spawned

## Verification
- Courier grep ran and returned empty
- Skill did NOT escalate to judgment
- Prompt includes "No existing project pattern found" note
- .draft lifecycle used
```

- [ ] **Step 3: Write courier_structural_empty_specdriven.md**

Create `tests/skill/scenarios/courier_structural_empty_specdriven.md`:

```markdown
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
```

- [ ] **Step 4: Commit**

```bash
git add tests/skill/scenarios/courier_structural_found.md \
        tests/skill/scenarios/courier_structural_empty_framework.md \
        tests/skill/scenarios/courier_structural_empty_specdriven.md
git commit -m "test: add Context Courier structural scenarios"
```

---

### Task 4: Update Step 3 — extend Context Courier for structural tasks

**Files:**
- Modify: `skills/route-tasks/SKILL.md` (Step 3 section)

- [ ] **Step 1: Replace the entire Step 3 section**

In `skills/route-tasks/SKILL.md`, find and replace:

Old (entire Step 3):
```
## Step 3: Context Courier (mechanical tasks only)

You MUST gather pattern context before calling `local_llm`. Do not assume a pattern exists — verify it.

1. Identify the pattern type from the task (CRUD, serializer, test stub, migration, etc.)
2. Search the codebase:
   ```bash
   grep -r "<relevant keyword>" src/ --include="*.py" -l 2>/dev/null
   ```
3. **Check the result explicitly:**
   - **No files returned / empty output:** The task is not actually mechanical. Escalate to Agent (Step 4b, judgment path). Do not proceed with local_llm.
   - **Files returned:** Read the most relevant file. Extract 30–50 lines of the closest matching example.

4. Assemble the augmented prompt. Keep total length under 16000 characters:

   ```
   system: "You are a code generator. Follow the provided patterns exactly. Output only code. No explanation."

   prompt: |
     ## Existing pattern (<filepath> lines <N>-<M>):
     <excerpt from file>

     ## Task:
     <task description>
     Follow the exact naming conventions, structure, and patterns shown above.
   ```

5. Proceed to Step 4 (local_llm execution path).
```

New:
```
## Step 3: Context Courier

Runs for both mechanical and structural tasks. Do not assume a pattern exists — verify it.

When entering Step 3 without a prior classification from Step 2 (e.g., `local-only` mode), use the **Mechanical tasks** section.

### Mechanical tasks

1. Identify the pattern type from the task (CRUD, serializer, test stub, migration, etc.)
2. Search the codebase:
   ```bash
   grep -r "<relevant keyword>" src/ --include="*.py" -l 2>/dev/null
   ```
3. **Check the result explicitly:**
   - **No files returned / empty output:** The task is not actually mechanical. Escalate to Agent (judgment path). Do not proceed with local_llm.
   - **Files returned:** Read the most relevant file. Extract 30–50 lines of the closest matching example.

### Structural tasks

1. Identify the convention type (Response model, exception handling, route pattern, model inheritance, fixture style, etc.)
2. Search the codebase for style conventions:
   ```bash
   grep -r "<relevant keyword>" . --include="*.py" -l 2>/dev/null
   ```
   Example keywords: `HTTPException` for error handling, `BaseModel` for Pydantic conventions, `pytest.fixture` for fixture style, `APIRouter` for route structure.
3. **Check the result:**
   - **Files returned:** Read the most relevant file. Extract 30–50 lines showing the project's style.
   - **No files returned, framework-known task:** Proceed. Add to prompt: "No existing project pattern found. Follow framework defaults."
   - **No files returned, spec-driven only (not framework-known):** Escalate to Agent (judgment path). Do not proceed with local_llm.

### Assemble the augmented prompt (both tiers)

Keep total length under 16000 characters:

```
system: "You are a code generator. Follow the provided patterns exactly. Output only code. No explanation."

prompt: |
  ## Existing pattern (<filepath> lines <N>-<M>):
  <excerpt from file>

  ## Task:
  <task description>
  Follow the exact naming conventions, structure, and patterns shown above.
```

For structural tasks where no project pattern was found, replace the "Existing pattern" block with:
```
  ## Note:
  No existing project pattern found. Follow framework defaults for <framework name>.
```

Proceed to Step 4.
```

- [ ] **Step 2: Verify the edit**

```bash
grep -n "Mechanical tasks\|Structural tasks\|Assemble the augmented" skills/route-tasks/SKILL.md
```

Expected: lines for each new subsection header.

- [ ] **Step 3: Commit**

```bash
git add skills/route-tasks/SKILL.md
git commit -m "feat: extend Context Courier to handle structural tasks"
```

---

### Task 5: Structural execution path scenario files

**Files:**
- Create: `tests/skill/scenarios/structural_patch.md`
- Create: `tests/skill/scenarios/structural_rewrite.md`
- Create: `tests/skill/scenarios/structural_reject.md`
- Create: `tests/skill/scenarios/structural_pytest_trivial.md`
- Create: `tests/skill/scenarios/structural_pytest_nontrivial.md`

- [ ] **Step 1: Write structural_patch.md**

Create `tests/skill/scenarios/structural_patch.md`:

```markdown
# Scenario: Structural Path — Agent Patches Draft

## Setup
- Project has `src/api/users.py` with existing FastAPI routes
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a FastAPI route POST /posts that creates a post, following existing route patterns"

## Expected Behavior
1. Classified as structural (FastAPI route — framework-known)
2. Courier greps for `APIRouter`, finds users.py, extracts 40 lines
3. local_llm called with style excerpt, returns POST /posts handler code
4. Code written to `src/api/posts.py.draft`
5. Agent review spawned — draft has minor issue (missing response_model)
6. Agent outputs PATCH and adds `response_model=PostResponse` inline
7. Skill renames `src/api/posts.py.draft` → `src/api/posts.py`
8. pytest passes
9. Committed as `feat: add POST /posts route`

## Verification
- .draft file used (not written directly to posts.py)
- Agent review spawned before rename
- Agent output was PATCH (not REWRITE or REJECT)
- Final file is posts.py (no .draft suffix)
- pytest passed
```

- [ ] **Step 2: Write structural_rewrite.md**

Create `tests/skill/scenarios/structural_rewrite.md`:

```markdown
# Scenario: Structural Path — Agent Rewrites Draft

## Setup
- Project has `src/api/users.py` with existing FastAPI routes using dependency injection
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a FastAPI route GET /posts that returns a paginated list of posts"

## Expected Behavior
1. Classified as structural (FastAPI route — framework-known)
2. Courier greps for `APIRouter`, finds users.py, extracts style excerpt
3. local_llm returns route code that ignores existing dependency injection pattern
4. Code written to `src/api/posts.py.draft`
5. Agent review spawned — draft is significantly wrong (missing db dependency, wrong return type)
6. Agent outputs REWRITE and produces corrected version using project's dependency pattern
7. Agent's rewrite overwrites `src/api/posts.py.draft`
8. Skill renames draft → `src/api/posts.py`
9. pytest passes, committed

## Verification
- Agent output was REWRITE
- .draft was overwritten before rename
- Final committed code uses project's dependency injection pattern
```

- [ ] **Step 3: Write structural_reject.md**

Create `tests/skill/scenarios/structural_reject.md`:

```markdown
# Scenario: Structural Path — Agent Rejects Draft (Judgment Task in Disguise)

## Setup
- Project has existing route files
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a FastAPI route for user authentication that handles OAuth2 token exchange"

## Expected Behavior
1. Classified initially as structural (FastAPI route — framework-known)
2. Courier greps for route patterns, finds existing routes
3. local_llm returns basic route code
4. Code written to `src/api/auth.py.draft`
5. Agent review spawned
6. Agent outputs REJECT: "This task involves OAuth2 token exchange and credential handling — security-sensitive logic requiring judgment routing."
7. Skill deletes `src/api/auth.py.draft`
8. Task re-classified as judgment
9. Agent spawned with full task description and security context

## Verification
- Agent review output was REJECT with reason
- .draft file was deleted (not renamed)
- Task escalated to judgment path
- Final Agent handles the auth implementation
```

- [ ] **Step 4: Write structural_pytest_trivial.md**

Create `tests/skill/scenarios/structural_pytest_trivial.md`:

```markdown
# Scenario: Structural Path — Trivial pytest Failure (Fix Inline)

## Setup
- Project has existing Pydantic models
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a Pydantic model UserUpdate with fields: name (str, optional), email (EmailStr, optional)"

## Expected Behavior
1. Classified as structural (Pydantic model — framework-known)
2. Courier finds existing model file, extracts style
3. local_llm returns model code missing `from typing import Optional` import
4. Code written to `src/schemas/user_update.py.draft`
5. Agent reviews, outputs PATCH (adds Optional import inline)
6. Draft renamed to `src/schemas/user_update.py`
7. pytest fails: `NameError: name 'Optional' not found`
8. Skill inspects failure: single missing import — `Optional` IS used elsewhere in the file (in another field)
9. Trivial fix: add `from typing import Optional` to imports, re-run pytest once
10. pytest passes, committed

## Trivial definition (for reference)
Trivial = single-line syntax error, missing import already present elsewhere in the file,
or typo in variable/function name. This scenario qualifies because Optional is in the same file.

## Verification
- Skill fixed inline without escalating
- Only one re-run of pytest
- Committed successfully
```

- [ ] **Step 5: Write structural_pytest_nontrivial.md**

Create `tests/skill/scenarios/structural_pytest_nontrivial.md`:

```markdown
# Scenario: Structural Path — Non-Trivial pytest Failure (Escalate)

## Setup
- Project has existing FastAPI routes with integration tests
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid

## Input Task
"Add a Pydantic model PostCreate and wire it as the request body for POST /posts"

## Expected Behavior
1. Classified as structural (Pydantic model — framework-known)
2. local_llm returns model and route code
3. Agent reviews, outputs PATCH for minor style issue
4. Draft renamed, pytest run
5. pytest fails: integration test fails because route handler references `PostCreate.content` but model defines `PostCreate.body`
6. Failure is non-trivial: logic error requiring understanding of test expectations
7. Skill escalates to judgment path
8. Agent spawned with full task + draft content as context: "The structural draft was committed but pytest failed with a logic error: [paste failure]. Draft content: [paste code]. Fix the implementation."

## Verification
- Skill did NOT attempt inline fix (logic error, not trivial)
- Escalated to judgment with draft content passed as context
- Agent handles the non-trivial fix
```

- [ ] **Step 6: Commit scenario files**

```bash
git add tests/skill/scenarios/structural_patch.md \
        tests/skill/scenarios/structural_rewrite.md \
        tests/skill/scenarios/structural_reject.md \
        tests/skill/scenarios/structural_pytest_trivial.md \
        tests/skill/scenarios/structural_pytest_nontrivial.md
git commit -m "test: add structural execution path scenarios"
```

---

### Task 6: Update Step 4 — add structural execution path

**Files:**
- Modify: `skills/route-tasks/SKILL.md` (Step 4 section)

- [ ] **Step 1: Update trivial failure definition in mechanical path**

In `skills/route-tasks/SKILL.md`, find and replace:

Old:
```
4. If tests fail with trivial issues (missing import, typo): fix inline. If non-trivial: escalate to Agent.
```

New:
```
4. If tests fail:
   - **Trivial** (fix inline): single-line syntax error, missing import already present elsewhere in the file, typo in variable/function name → fix inline, re-run pytest once
   - **Non-trivial** (escalate): logic error, multiple file changes required, new dependency needed → escalate to Agent
```

- [ ] **Step 2: Add structural path between mechanical and judgment**

In `skills/route-tasks/SKILL.md`, find and replace:

Old:
```
Log this task to `~/.pedalpoint/fallback-log.md` only if circuit is OPEN (fallback active).

### Judgment path (Agent)
```

New:
```
Log this task to `~/.pedalpoint/fallback-log.md` only if circuit is OPEN (fallback active).

### Structural path (local_llm draft + Agent review)

Call the `local_llm` tool with the augmented prompt from Step 3:
```
local_llm(prompt=<augmented prompt>, system="You are a code generator. Follow the provided patterns exactly. Output only code. No explanation.")
```

1. `git checkout -b feat/<task-slug>` (or appropriate branch prefix)
2. Write the returned code to `<target_file>.draft` (NOT the real filename)
3. Spawn Agent review:
   ```
   Review <target_file>.draft against the task description below.
   - If structurally sound with only minor issues: patch the draft inline and output PATCH.
   - If significantly wrong but salvageable: rewrite the draft completely and output REWRITE.
   - If this is a judgment task in disguise or cannot be fixed mechanically: output REJECT and state the reason.

   Task: <task description>
   ```
4. Agent result:
   - `PATCH` → Agent has edited `.draft` inline; proceed to step 5
   - `REWRITE` → Agent has overwritten `.draft`; proceed to step 5
   - `REJECT` → delete `.draft`, re-classify as judgment, run judgment path
5. Rename `<target_file>.draft` → `<target_file>`
6. Run test suite: `pytest tests/ -x -q`
7. If tests fail:
   - **Trivial** (fix inline): single-line syntax error, missing import already present elsewhere in the file, typo in variable/function name → fix inline, re-run pytest once
   - **Non-trivial** (escalate): logic error, multiple file changes required, new dependency needed → escalate to judgment path; pass draft content as context to Agent
8. Commit using Conventional Commits format
9. Mark task complete in the plan

Log this task to `~/.pedalpoint/fallback-log.md` only if circuit is OPEN or Agent review was skipped due to error (see Step 4b).

### Judgment path (Agent)
```

- [ ] **Step 3: Verify structural path appears in the file**

```bash
grep -n "Structural path\|\.draft\|PATCH\|REWRITE\|REJECT" skills/route-tasks/SKILL.md
```

Expected: multiple lines in the new structural path section.

- [ ] **Step 4: Commit**

```bash
git add skills/route-tasks/SKILL.md
git commit -m "feat: add structural execution path to Step 4"
```

---

### Task 7: Error handling scenario files

**Files:**
- Create: `tests/skill/scenarios/structural_402_fallback.md`
- Create: `tests/skill/scenarios/structural_429_retry.md`
- Create: `tests/skill/scenarios/structural_circuit_open.md`

- [ ] **Step 1: Write structural_402_fallback.md**

Create `tests/skill/scenarios/structural_402_fallback.md`:

```markdown
# Scenario: Structural Path — 402 Quota Error During Agent Review

## Setup
- Circuit breaker: CLOSED at task start
- PEDALPOINT_MODE: hybrid
- local_llm: available

## Input Task
"Add a Pydantic model OrderCreate with fields: items (list[str]), total (float)"

## Expected Behavior
1. Classified as structural (Pydantic model)
2. Courier runs, local_llm drafts code
3. Code written to `src/schemas/order.py.draft`
4. Agent review spawn fails with 402 quota error
5. Skill writes OPEN circuit state to `~/.pedalpoint/state.json`:
   ```json
   {
     "circuit": "open",
     "reason": "402_quota",
     "opened_at": "<current UTC ISO>",
     "expires": "<current UTC + 60 min ISO>",
     "failure_count": 1,
     "fallback_duration_minutes": 60,
     "tasks_rerouted": 0
   }
   ```
6. Skill renames `src/schemas/order.py.draft` → `src/schemas/order.py` (uses draft content as-is, does NOT re-run local_llm)
7. Skill appends HIGH PRIORITY entry to `~/.pedalpoint/fallback-log.md`:
   ```
   ## <ISO timestamp> — structural draft committed unreviewed (reason: 402_quota) ⚠ HIGH PRIORITY
   **Task:** Add a Pydantic model OrderCreate...
   **Risk:** Agent review skipped due to quota. Logic correctness unverified.
   **Draft preview:** <first 200 chars of draft>
   ---
   ```
8. Commits with conventional format

## Verification
- Circuit opened (state.json written)
- .draft renamed to real file (not deleted, not re-run)
- HIGH PRIORITY entry in fallback-log.md
- Subsequent tasks will see OPEN circuit and skip to mechanical path
```

- [ ] **Step 2: Write structural_429_retry.md**

Create `tests/skill/scenarios/structural_429_retry.md`:

```markdown
# Scenario: Structural Path — 429 Rate Limit During Agent Review

## Setup
- Circuit breaker: CLOSED
- PEDALPOINT_MODE: hybrid
- Agent returns 429 on first review attempt, and again on retry

## Input Task
"Add a dataclass `Config` with fields: host (str), port (int), debug (bool = False)"

## Expected Behavior
1. Classified as structural (Python dataclass — framework-known)
2. local_llm drafts code, written to `src/config.py.draft`
3. Agent review spawn fails with 429
4. Skill waits 30 seconds
5. Retry: Agent review spawn fails with 429 again
6. Skill renames `src/config.py.draft` → `src/config.py` (use draft as-is)
7. Commit message flagged: `feat: add Config dataclass [unreviewed]`
8. Standard fallback log entry (NOT high priority):
   ```
   ## <ISO timestamp> — structural draft committed unreviewed (reason: 429_rate_limit)
   **Task:** Add a dataclass Config...
   **Draft preview:** <first 200 chars>
   ---
   ```
9. Circuit stays CLOSED (429 is not a quota error)

## Verification
- Waited 30s between attempts (one retry only)
- Commit message includes [unreviewed] flag
- Standard fallback log entry (no ⚠ HIGH PRIORITY)
- Circuit still CLOSED after task
```

- [ ] **Step 3: Write structural_circuit_open.md**

Create `tests/skill/scenarios/structural_circuit_open.md`:

```markdown
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
```

- [ ] **Step 4: Commit**

```bash
git add tests/skill/scenarios/structural_402_fallback.md \
        tests/skill/scenarios/structural_429_retry.md \
        tests/skill/scenarios/structural_circuit_open.md
git commit -m "test: add structural error handling scenarios"
```

---

### Task 8: Update Step 4b — structural review error handling and fallback log formats

**Files:**
- Modify: `skills/route-tasks/SKILL.md` (Step 4b section)

- [ ] **Step 1: Add structural review error table after existing Step 4b table**

In `skills/route-tasks/SKILL.md`, find and replace:

Old:
```
**Writing OPEN state** (on 402 quota error):
```

New (insert structural error section before "Writing OPEN state"):
```
**Structural path Agent review errors:**

When the Agent review spawn (step 3 of the structural path) fails:

| Error pattern | Action |
|---|---|
| `429` or `rate.?limit` | Wait 30s, retry review once. Still failing: rename `.draft` → target file, flag commit message `[unreviewed]`, log standard structural fallback entry. |
| `402`, `quota`, `billing`, `insufficient` | Write OPEN state (see below). Rename `.draft` → target file (use draft content as-is; do not re-run local_llm). Log HIGH PRIORITY structural fallback entry. |
| `529`, `overload`, `capacity` | Rename `.draft` → target file, flag commit message `[unreviewed]`, log standard structural fallback entry. Circuit stays CLOSED. |
| `timeout`, `connection` | Delete `.draft`. Re-classify as judgment. Run judgment path. |

**Writing OPEN state** (on 402 quota error):
```

- [ ] **Step 2: Add structural fallback log formats**

In `skills/route-tasks/SKILL.md`, find and replace:

Old:
```
**Logging rerouted tasks** — append to `~/.pedalpoint/fallback-log.md`:
```markdown
## <ISO timestamp> — task rerouted (reason: <reason>)
**Task:** <task description>
**Response preview:** <first 200 chars of local_llm response>
---
```
```

New:
```
**Logging rerouted tasks** — append to `~/.pedalpoint/fallback-log.md`:
```markdown
## <ISO timestamp> — task rerouted (reason: <reason>)
**Task:** <task description>
**Response preview:** <first 200 chars of local_llm response>
---
```

**Logging structural fallbacks (429/529 review skip)** — append to `~/.pedalpoint/fallback-log.md`:
```markdown
## <ISO timestamp> — structural draft committed unreviewed (reason: <reason>)
**Task:** <task description>
**Draft preview:** <first 200 chars of local_llm response>
---
```

**Logging structural fallbacks (402 quota or circuit OPEN mid-task)** — append to `~/.pedalpoint/fallback-log.md`:
```markdown
## <ISO timestamp> — structural draft committed unreviewed (reason: <reason>) ⚠ HIGH PRIORITY
**Task:** <task description>
**Risk:** Agent review skipped due to quota. Logic correctness unverified.
**Draft preview:** <first 200 chars of local_llm response>
---
```
```

- [ ] **Step 3: Verify edits**

```bash
grep -n "Structural path Agent review\|HIGH PRIORITY\|structural draft committed" skills/route-tasks/SKILL.md
```

Expected: lines for new structural error section and both new log formats.

- [ ] **Step 4: Commit**

```bash
git add skills/route-tasks/SKILL.md
git commit -m "feat: add structural path error handling and HIGH PRIORITY log format to Step 4b"
```

---

### Task 9: Update Step 5 — post-session review

**Files:**
- Modify: `skills/route-tasks/SKILL.md` (Step 5 section)

- [ ] **Step 1: Replace Step 5 content**

In `skills/route-tasks/SKILL.md`, find and replace:

Old:
```
## Step 5: Post-Session Review

After all tasks in the plan are complete:

1. Check `~/.pedalpoint/fallback-log.md` for entries added in this session
2. Count entries since session start
3. If count > 0:
   > "N tasks ran on local LLM during fallback. Run Claude review pass now? (y/n)"
4. If user says yes: spawn Agent with prompt:
   > "Review the work done by local LLM during fallback. Check `~/.pedalpoint/fallback-log.md` for the task list, then run `git log --oneline -<N>` and `git diff HEAD~<N>` to see the changes. Identify any issues with code quality, correctness, or missed requirements and summarize your findings."
```

New:
```
## Step 5: Post-Session Review

After all tasks in the plan are complete:

1. Check `~/.pedalpoint/fallback-log.md` for entries added in this session
2. Count total entries since session start (N)
3. Count entries containing `⚠ HIGH PRIORITY` (K)
4. If N > 0:
   > "N tasks ran on local LLM during fallback. K structural drafts marked HIGH PRIORITY (quota fallback — Agent review skipped). Review HIGH PRIORITY items first. Run Claude review pass now? (y/n)"
5. If user says yes: spawn Agent with prompt:
   > "Review the work done by local LLM during fallback. Check `~/.pedalpoint/fallback-log.md` for the task list — prioritize any entries marked ⚠ HIGH PRIORITY first, as these were committed without Agent review due to quota exhaustion. Then run `git log --oneline -<N>` and `git diff HEAD~<N>` to see the changes. Identify any issues with code quality, correctness, or missed requirements and summarize your findings."
```

- [ ] **Step 2: Verify**

```bash
grep -n "HIGH PRIORITY\|K structural" skills/route-tasks/SKILL.md | tail -5
```

Expected: lines in Step 5 mentioning HIGH PRIORITY count.

- [ ] **Step 3: Commit**

```bash
git add skills/route-tasks/SKILL.md
git commit -m "feat: update Step 5 post-session review for structural draft tracking"
```

---

### Task 10: Documentation updates

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update README.md hybrid mode description**

In `README.md`, find and replace:

Old:
```
| `hybrid` | default | Claude classifies each task |
```

New:
```
| `hybrid` | default | Claude classifies each task into mechanical (local LLM direct), structural (local LLM draft + Agent review), or judgment (Agent only) |
```

- [ ] **Step 2: Update CLAUDE.md Key Design Decisions**

In `CLAUDE.md`, find and replace:

Old:
```
- **Thin server, smart skill:** Server is a pure HTTP proxy. All routing logic lives in the skill. Server never touches `~/.pedalpoint/state.json`.
```

New:
```
- **Thin server, smart skill:** Server is a pure HTTP proxy. All routing logic lives in the skill. Server never touches `~/.pedalpoint/state.json`.
- **Three-tier routing (junior/senior model):** Local LLM = junior dev, Agent = senior dev. Mechanical tasks go to local LLM directly. Structural tasks (framework-known patterns + spec-driven tasks) go to local LLM for a draft, then Agent reviews before commit (`.draft` lifecycle). Judgment tasks (architecture, debugging, security) go to Agent only.
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: update README and CLAUDE.md with three-tier routing model"
```

---

### Task 11: PR and merge

- [ ] **Step 1: Push branch**

```bash
git push -u origin feat/junior-senior-routing
```

- [ ] **Step 2: Open PR**

```bash
gh pr create \
  --title "feat: junior/senior routing model for route-tasks skill" \
  --body "$(cat <<'EOF'
## Summary
- Adds structural routing tier: local LLM drafts, Agent reviews before commit
- Extends Context Courier to grep for style conventions on structural tasks
- `.draft` file lifecycle prevents unreviewed code from landing in workspace
- HIGH PRIORITY log entries flag quota-triggered review skips for post-session follow-up
- 15 new scenario files covering all classification and execution paths

## Test plan
- [ ] Review scenario files in `tests/skill/scenarios/` for accuracy
- [ ] Manual walkthrough: invoke `/route-tasks` on a pytest fixture task — verify structural path executes with Agent review
- [ ] Manual walkthrough: invoke on a CRUD task — verify mechanical path unchanged
- [ ] Check fallback-log format after simulating a 402 scenario

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Merge**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 4: Clean up**

```bash
git checkout main && git pull
```
