---
name: route-tasks
description: Execute implementation plan tasks with automatic routing between local LLM and Claude. Replaces subagent-driven-development with quota-aware circuit-breaker routing. Use when executing any implementation plan in a pedalpoint-enabled project.
---

# Pedalpoint: Intelligent Task Router

You are executing an implementation plan. For each task, follow these steps exactly.

## Prerequisites Check

Verify the `local_llm` MCP tool is available. If it is not listed in your available tools:
> ⚠ pedalpoint MCP server not connected. Run `pedalpoint-server` in a terminal to diagnose. Falling back to Agent for all tasks.

Fall back to Agent for all tasks and skip the remaining steps.

If `local_llm` is listed, call it with a minimal probe prompt (`"ping"`). If it returns a connection error:
> ⚠ Ollama unreachable — run `ollama serve` (or open Ollama.app on macOS) to enable local routing. Falling back to Agent for all tasks.

Fall back to Agent for all tasks and skip the remaining steps.

Check `PEDALPOINT_MODE` environment variable:
- `local-only` → skip Step 2 classification, route ALL tasks through Step 3 (Context Courier) to local_llm
- `passthrough` → skip Steps 2–4, route ALL tasks to Agent spawns
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
- If current time < expires: skip to Step 4 (local_llm, no classification)
- If current time >= expires: proceed to Step 1b (HALF-OPEN probe)

### Step 1b: HALF-OPEN Probe

Spawn a minimal Agent with prompt: `"Respond with only the word ok"`.

- **Agent succeeds:** Write `{"circuit":"closed"}` to `~/.pedalpoint/state.json`. Proceed to Step 2.
- **Agent fails with 402/quota/billing/insufficient:** Read existing state, double the `fallback_duration_minutes` and increment `failure_count`, write updated OPEN state. Proceed to Step 4.
- **Agent fails with 429/rate-limit:** Wait 30 seconds. Retry probe once. If still failing, treat as transient — proceed to Step 2.

---

## Step 2: Classify the Task

Read the task description. Apply these rules:

### Route to `local_llm` (mechanical) when ALL apply:
- Generates code that matches an established pattern already in the codebase
- No architectural decision required
- No cross-system integration
- No security-sensitive logic (auth, payments, tokens, credentials)
- Pattern can be verified by grep/Read (see Step 3)

**Examples:** generate CRUD following an existing CRUD file, write test function stubs, add type hints to existing functions, generate a config file following an existing template, write a serializer matching the existing serializer pattern.

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

---

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

---

## Step 4: Execute the Task

### Mechanical path (local_llm)

Call the `local_llm` tool with the augmented prompt from Step 3:
```
local_llm(prompt=<augmented prompt>, system="You are a code generator. Follow the provided patterns exactly. Output only code. No explanation.")
```

Apply the returned string:
1. `git checkout -b feat/<task-slug>` (or appropriate branch prefix)
2. Write the returned code to the target file using Write/Edit tools
3. Run the test suite: `pytest tests/ -x -q`
4. If tests fail with trivial issues (missing import, typo): fix inline. If non-trivial: escalate to Agent.
5. Commit using Conventional Commits format
6. Mark task complete in the plan

Log this task to `~/.pedalpoint/fallback-log.md` only if circuit is OPEN (fallback active).

### Judgment path (Agent)

Spawn an Agent with:
- The full task description
- Relevant file paths from the plan
- Any context from previous tasks that affects this one
- Instruction to follow existing codebase patterns

Monitor the Agent spawn result. On error, proceed to Step 4b.

### Step 4b: Agent Error Handling

Parse the error text from the failed Agent spawn:

| Error pattern | Action |
|---|---|
| `429` or `rate.?limit` | Wait 30s, retry (up to 3 times). After 3 failures: route this task only to local_llm (circuit stays CLOSED) |
| `402`, `quota`, `billing`, `insufficient` | Write OPEN state to `~/.pedalpoint/state.json` (see below). Re-route this task to local_llm via Step 3. |
| `529`, `overload`, `capacity` | Route this task only to local_llm. Circuit stays CLOSED for next task. |
| `timeout`, `connection` | Print `⚠ local LLM unreachable — falling back to Claude (run \`ollama serve\` to restore)`. Retry once. If still failing, treat as 529. |

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

**Logging rerouted tasks** — append to `~/.pedalpoint/fallback-log.md`:
```markdown
## <ISO timestamp> — task rerouted (reason: <reason>)
**Task:** <task description>
**Response preview:** <first 200 chars of local_llm response>
---
```

---

## Step 5: Post-Session Review

After all tasks in the plan are complete:

1. Check `~/.pedalpoint/fallback-log.md` for entries added in this session
2. Count entries since session start
3. If count > 0:
   > "N tasks ran on local LLM during fallback. Run Claude review pass now? (y/n)"
4. If user says yes: spawn Agent with prompt:
   > "Review the work done by local LLM during fallback. Check `~/.pedalpoint/fallback-log.md` for the task list, then run `git log --oneline -<N>` and `git diff HEAD~<N>` to see the changes. Identify any issues with code quality, correctness, or missed requirements and summarize your findings."
