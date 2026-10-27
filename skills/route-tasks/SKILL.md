---
name: route-tasks
description: Execute implementation plan tasks with automatic routing between local LLM and Claude. Replaces subagent-driven-development with quota-aware circuit-breaker routing. Use when executing any implementation plan in a pedalpoint-enabled project.
---

# Pedalpoint: Intelligent Task Router

You are executing an implementation plan. For each task, follow these steps exactly.

**The point of local handoffs is to save Claude output tokens.** The pedalpoint server writes the local model's code straight to a `.draft` file — you never re-type it. You only read the draft, fix what's wrong, and promote it with `mv`. Never paste code into a `task` argument; pass file paths instead.

## Prerequisites Check

Verify the `local_llm` and `local_llm_status` MCP tools are available.
- **Neither is listed:**
  > ⚠ pedalpoint MCP server not connected. Run `pedalpoint doctor` in a terminal to diagnose. Falling back to Agent for all tasks.
- **`local_llm` is listed but `local_llm_status` is not** (a pre-0.4 server):
  > ⚠ pedalpoint server is older than this skill — re-run install.sh

In both cases fall back to Agent for all tasks and skip the remaining steps.

Call `local_llm_status`. It returns JSON: `backend`, `model`, `base_url`, `reachable`, `repo_root`, `server_version`, `autostart`, `idle_minutes`.
- **`server_version` missing** (in this or any later pedalpoint tool result):
  > ⚠ pedalpoint server is older than this skill — re-run install.sh
- **`reachable` is false and `autostart` is true:** not a problem. The server starts the model on the first `local_llm` call (that call takes ~10s longer) and stops it after `idle_minutes` without calls. Print nothing and continue.
- **`reachable` is false otherwise:**
  > ⚠ `<MLX|Ollama>` unreachable — start it with: `<hint>`

  Hint: backend `mlx` → `mlx_lm.server --model <model>`; backend `ollama` → `ollama serve`. Fall back to Agent for all tasks and skip the remaining steps.
- **`repo_root` is null:**
  > ⚠ pedalpoint server is not running inside a git repo — local handoffs disabled.

  Fall back to Agent for all tasks.

Check `PEDALPOINT_MODE` environment variable:
- `local-only` → skip Step 2 classification, route ALL tasks through Step 3 (Context Courier) to the local path. Skip rule is OFF.
- `passthrough` → skip Steps 2–4, route ALL tasks to Agent spawns. Never hand off.
- `hybrid` (default or unset) → follow normal flow below

---

## Step 1: Read Circuit Breaker State

Before executing each task, run:

```bash
cat ~/.pedalpoint/state.json 2>/dev/null || echo '{"circuit":"closed"}'
```

Parse the JSON:

**If `circuit` is `"closed"` or file absent:** proceed to Step 2.

**If `circuit` is `"open"`:**
- Check `expires` field vs current time (`date -u +%Y-%m-%dT%H:%M:%SZ`)
- If current time < expires: skip Step 2, run Step 3 (mechanical mode), then the **open-circuit path** in Step 4
- If current time >= expires: proceed to Step 1b (HALF-OPEN probe)

**If `circuit` is `"api_fallback"`:**
- Check `expires` field vs current time (`date -u +%Y-%m-%dT%H:%M:%SZ`)
- If current time < expires: proceed to Step 2 with **API mode active** (judgment tasks go to `claude_api` instead of Agent; see Step 4)
- If current time >= expires: proceed to Step 1b (HALF-OPEN probe)

### Step 1b: HALF-OPEN Probe

Spawn a minimal Agent with prompt: `"Respond with only the word ok"`.

- **Agent succeeds:** Write `{"circuit":"closed"}` to `~/.pedalpoint/state.json`. Proceed to Step 2.
- **Agent fails with 402/quota/billing/insufficient/upgrade.*plan/plan.*limit/usage.{0,20}limit:**
  - If current state is `open`: double duration, increment `failure_count`, write updated OPEN state. Proceed to Step 3 then the open-circuit path.
  - If current state is `api_fallback`: double duration, increment `failure_count`, write updated `api_fallback` state (circuit stays `api_fallback` — claude_api still available). Proceed to Step 2.
- **Agent fails with 429/rate-limit:** Wait 30 seconds. Retry probe once. If still failing, treat as transient — proceed to Step 2.
- **(any other / unrecognized error):** Treat as hard quota. Double duration, increment `failure_count`, write updated state. Log `⚠ HIGH PRIORITY` entry with full error text. Proceed to the open-circuit path if circuit is `open`; proceed to Step 2 if circuit is `api_fallback`.

---

## Step 2: Classify the Task

Read the task description. Apply these rules:

### Local draft — mechanical, when ALL apply:
- Generates code that matches an established pattern already in the codebase
- No architectural decision required
- No cross-system integration
- No security-sensitive logic (auth, payments, tokens, credentials)
- Pattern can be verified by grep/Read (see Step 3)

**Examples:** generate CRUD following an existing CRUD file, write test function stubs, add type hints to existing functions, generate a config file following an existing template, write a serializer matching the existing serializer pattern.

### Local draft — structural, when ANY apply:
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

### Skip rule (hybrid mode, circuit closed or api_fallback)

If a mechanical or structural task's expected **lines changed** (not file size) is under ~30, do it yourself directly with Edit/Write — the handoff overhead costs more than the work. No `local_llm` call, no `record_outcome`.

---

## Step 3: Context Courier

Runs for both mechanical and structural tasks. Do not assume a pattern exists — verify it.

When entering Step 3 without a prior classification from Step 2 (e.g., `local-only` mode or open circuit), use the **Mechanical tasks** section.

### Mechanical tasks

1. Identify the pattern type from the task (CRUD, serializer, test stub, migration, etc.)
2. Search the codebase:
   ```bash
   grep -rn "<relevant keyword>" src/ --include="*.py" 2>/dev/null
   ```
3. **Check the result explicitly:**
   - **No files returned / empty output:** The task is not actually mechanical. Escalate to Agent (judgment path). Do not proceed with a local draft.
   - **Files returned:** Pick the closest matching example and its 30–50 line range (use the `grep -n` line numbers; Read only if needed to find the range).

### Structural tasks

1. Identify the convention type (Response model, exception handling, route pattern, model inheritance, fixture style, etc.)
2. Search the codebase for style conventions:
   ```bash
   grep -rn "<relevant keyword>" . --include="*.py" 2>/dev/null
   ```
   Example keywords: `HTTPException` for error handling, `BaseModel` for Pydantic conventions, `pytest.fixture` for fixture style, `APIRouter` for route structure.
3. **Check the result:**
   - **Files returned:** Pick the 30–50 line range that shows the project's style.
   - **No files returned, framework-known task:** Proceed. Add to `task`: "No existing project pattern found. Follow framework defaults for <framework name>."
   - **No files returned, spec-driven only (not framework-known):** Escalate to Agent (judgment path). Do not proceed with a local draft.

### Build the handoff arguments

- `target_path`: the file to create or replace (relative to your working directory's repo root).
- `worktree`: your current working directory (absolute). Always pass it. The server started in whatever checkout the session opened in; if you have since moved into a git worktree, this is what makes the draft land in the worktree instead of the main checkout.
- `context_paths`: list of `"path"` or `"path:START-END"` (1-indexed, inclusive) from the courier. The server reads these files itself.
- `task`: the instruction in plain words, plus the framework note if any. **Never paste code into `task`.**

The server already sends the target file's current contents when editing an existing file.

---

## Step 4: Execute the Task

Start on a branch: `git checkout -b feat/<task-slug>` (or appropriate prefix).

### Local path (circuit closed — mechanical and structural)

1. Call `local_llm(task=<task>, target_path=<target>, context_paths=[...], worktree=<cwd>)`. It writes `<target>.draft` and returns JSON with `handoff_id`, `draft_path`, `lines`, `lines_changed`.
2. Read `<target>.draft`. Review it against the task.
3. Fix what's wrong with Edit on the `.draft` (or rewrite it if it's mostly wrong).
   - **Judgment task in disguise** (security-sensitive, needs design decisions): `rm <target>.draft`, `record_outcome(handoff_id, 1, "<reason>")`, then run the judgment path.
4. Promote: `mv <target>.draft <target>`
5. Run the test suite: `pytest tests/ -x -q`
6. If tests fail:
   - **Trivial** (fix inline): single-line syntax error, missing import whose usage is already present in the file, typo in variable/function name → fix inline, re-run pytest once
   - **Non-trivial** (escalate): logic error, multiple file changes required, new dependency needed → escalate to Agent with the task, the failure, and the file path
7. `record_outcome(handoff_id, score, note)` — score is **what you had to do** (including any test fixes):

   | Score | What Claude did |
   |---|---|
   | 7 | Accepted as-is |
   | 6 | Fixed 1–3 lines |
   | 5 | Several fixes, same file |
   | 4 | Rewrote part |
   | 3 | Rewrote most |
   | 2 | Started over, draft helped |
   | 1 | Started over, draft useless |

8. Commit using Conventional Commits format
9. Mark task complete in the plan

### API fallback path (circuit `api_fallback`)

Mechanical and structural tasks use the local path above unchanged. Judgment tasks call `claude_api(task=<task>, target_path=<target>, context_paths=[...], worktree=<cwd>)` instead of spawning an Agent. It has the same contract as `local_llm`: writes `<target>.draft`, returns JSON with `handoff_id`. Then follow local path steps 2–9.

### Open-circuit path (circuit `open` — Claude quota exhausted)

1. Call `local_llm(task, target_path, context_paths, worktree)` (skip rule OFF).
2. No review: `mv <target>.draft <target>`
3. Run `pytest tests/ -x -q`; trivial failures fixed inline only if possible without review.
4. Commit with `[unreviewed]` in the message.
5. Append a "task rerouted" entry to `~/.pedalpoint/fallback-log.md` (format below). Do NOT call `record_outcome`.

### Judgment path (Agent)

Spawn an Agent with:
- The full task description
- Relevant file paths from the plan
- Any context from previous tasks that affects this one
- Instruction to follow existing codebase patterns

Monitor the Agent spawn result. On error, proceed to Step 4b.

### Step 4b: Error Handling

**Draft errors (`local_llm` / `claude_api`) — check this table FIRST. None of these are circuit events; never change state.json for them:**

| Error text contains | Action |
|---|---|
| `outside the project repo`, `Not in a git repository`, `must be a file`, `is not a worktree of`, `is not inside a git worktree` | Do the task yourself directly. |
| `too large for local regeneration`, `Context too large` | Do the task yourself directly. |
| `Cannot read`, `Bad line range` | Fix the `context_paths` / `target_path` and retry once. Still failing: do the task yourself. |
| `Model returned empty output` | Retry once. Still empty: do the task yourself. |
| `Model output truncated` | Split the task into smaller files, or do it yourself. |
| `did not start within`, `exited while starting`, `mlx_lm.server not found` | Print the error (it names the log or the install fix). Do the task yourself. |
| `not reachable`, `timed out` (from `local_llm`) | Print `⚠ local LLM unreachable — falling back to Claude`. Do the task yourself. |
| `not found — run:` | Print the error (it contains the download command). Do the task yourself. |
| **any other `local_llm` error**, or a `claude_api` error that does not start with `HTTP `, `Anthropic API`, or `ANTHROPIC_API_KEY` | Do the task yourself directly. Never treat it as quota. |

In the **open-circuit path**, "do the task yourself" is not possible: skip the task, log it to `fallback-log.md` with the error text, and continue with the next task.

**Agent spawn errors (judgment path):**

| Error pattern | Action |
|---|---|
| `429` or `rate.?limit` | Wait 30s, retry (up to 3 times). After 3 failures: route this task only to the local path (circuit stays CLOSED) |
| `402`, `quota`, `billing`, `insufficient`, `upgrade.*plan`, `plan.*limit`, `usage.{0,20}limit`, `401`, `unauthorized`, `invalid.*key` | Write OPEN state if circuit was already `api_fallback`; write `api_fallback` state if circuit was `closed`. Re-route this task: if writing `api_fallback`, re-route to `claude_api`; if writing `open`, re-route to the open-circuit path via Step 3. |
| `529`, `overload`, `capacity` | Route this task only to the local path. Circuit stays CLOSED for next task. |
| **(any other / unrecognized error)** | Treat as hard quota. Write `api_fallback` state if circuit is `closed`; write OPEN state if circuit is `api_fallback`. Re-route this task to `claude_api` or the open-circuit path accordingly. Log `⚠ HIGH PRIORITY` entry with full error text. |

**`claude_api` API errors (circuit is `api_fallback`; only errors starting with `HTTP `, `Anthropic API`, or `ANTHROPIC_API_KEY`):**

| Error pattern | Action |
|---|---|
| `429` or `rate.?limit` | Wait 30s, retry once. Still failing: route this task to the local path; circuit stays `api_fallback`. |
| `402`, `quota`, `billing`, `insufficient`, `upgrade.*plan`, `plan.*limit`, `usage.{0,20}limit`, `401`, `unauthorized`, `invalid.*key`, `ANTHROPIC_API_KEY not set` | Write OPEN state with `failure_count=1` to `~/.pedalpoint/state.json`. Re-route this task to the open-circuit path via Step 3. |
| `529`, `overload`, `capacity` | Route this task only to the local path. Circuit stays `api_fallback`. |
| `Anthropic API not reachable` | Retry once. Still failing: route this task to the local path. Circuit stays `api_fallback`. |
| **(any other / unrecognized error)** | Write OPEN state with `failure_count=1`. Re-route this task to the open-circuit path via Step 3. Log `⚠ HIGH PRIORITY` entry with full error text. |

**Writing OPEN state** (on 402 quota error):
```json
{
  "circuit": "open",
  "reason": "402_quota",
  "opened_at": "<current UTC ISO timestamp>",
  "expires": "<current UTC + 60 minutes ISO timestamp>",
  "failure_count": 1,
  "fallback_duration_minutes": 60,
  "tasks_rerouted": 0
}
```
Write this to `~/.pedalpoint/state.json` using the Write tool.

**Logging open-circuit tasks** — append to `~/.pedalpoint/fallback-log.md`:
```markdown
## <ISO timestamp> — task rerouted (reason: <reason>)
**Task:** <task description>
**File:** <target path> (committed [unreviewed])
---
```

Use `⚠ HIGH PRIORITY` in the heading when the reason was an unrecognized error or the task was structural:
```markdown
## <ISO timestamp> — task rerouted (reason: <reason>) ⚠ HIGH PRIORITY
**Task:** <task description>
**Risk:** Claude review skipped due to quota. Logic correctness unverified.
**File:** <target path> (committed [unreviewed])
---
```

---

## Step 5: Post-Session Review

After all tasks in the plan are complete:

1. Check `~/.pedalpoint/fallback-log.md` for entries added in this session
2. Count total entries since session start (N)
3. Count entries containing `⚠ HIGH PRIORITY` (K)
4. If N > 0:
   > "N tasks ran on local LLM without Claude review (circuit open). K marked HIGH PRIORITY. Review HIGH PRIORITY items first. Run Claude review pass now? (y/n)"
5. If user says yes: spawn Agent with prompt:
   > "Review the work done by local LLM during fallback. Check `~/.pedalpoint/fallback-log.md` for the task list — prioritize any entries marked ⚠ HIGH PRIORITY first, as these were committed without review due to quota exhaustion. Then run `git log --oneline -<N>` and `git diff HEAD~<N>` to see the changes. Identify any issues with code quality, correctness, or missed requirements and summarize your findings."
6. Mention that `pedalpoint stats` shows how many Claude tokens the local handoffs saved.
