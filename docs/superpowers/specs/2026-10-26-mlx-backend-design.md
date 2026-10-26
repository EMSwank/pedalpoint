# pedalpoint v0.4 — MLX backend, draft-writing server, real savings metrics

## Intent

The user runs pedalpoint on a 16GB M4 MacBook Air (Claude Pro plan). The goal is
to **stretch each 5-hour Pro session as far as possible without upgrading to Max**.
Local models are a means to that, not the goal.

Two problems today:

1. **gemma4:12b via Ollama is too heavy for this machine.** With normal apps open,
   it drops available memory from ~8GB to <1GB, runs ~9.5 tok/s, and cold-loads
   in 15–41s. The user expects to run more apps, not fewer.
2. **The handoff likely costs more Claude tokens than it saves.** In
   `skills/route-tasks/SKILL.md` Step 4, Claude writes a prompt (with pasted code
   excerpts) — Claude output; then takes the returned code and re-types all of it
   via Write — Claude output again; structural tasks also spawn a fresh review
   Agent that rebuilds context. Net: Claude writes more than if it did the task
   itself. Transcripts show `local_llm` has never actually been called in any
   retained session, so there is no evidence it ever saved anything.

The user also wants **proof**: metrics showing whether handoffs pay off. They are
new to this kind of measurement; the design below picks the metrics.

## Goals

- Run a small, fast local model via MLX on Apple Silicon without bogging the machine down.
- Keep Ollama as a supported backend (so a future Linux box works), at near-zero extra cost.
- Eliminate Claude re-typing local-model output: the server writes a `.draft` file.
- Make Claude's review cheap: read the draft inline, no review subagent.
- Measure net tokens saved using real Claude token counts from Claude Code transcripts.

## Non-goals

- Linux-specific work or testing (Ollama path just keeps working as today).
- Streaming.
- Automatic model selection / switching.
- Reading the Claude Code usage bar (no API exists).

## Anti-goals

- Handoffs that cost more Claude tokens than they save. If metrics show this, the
  design failed even if everything "works".
- A local model that degrades the rest of the machine (swap storms, multi-GB spikes).
- The server ever writing a non-`.draft` file or anything outside the project repo.

## Constraints

- Hardware: 16GB unified memory, already carrying heavy swap with normal apps.
- Existing invariants in `CLAUDE.md` stay unless changed here: circuit breaker in
  skill, Context Courier grep-before-handoff, 402 vs 429 handling, TDD, coverage
  (circuit_breaker 100%, error_classifier 100%, server ≥90%).
- Transcript format (`~/.claude/projects/<slug>/<session>.jsonl`) is undocumented and
  may change; anything reading it must degrade gracefully.

## Decisions made with the user

1. **Backend setting.** `PEDALPOINT_BACKEND=mlx|ollama`. Both serve the OpenAI-style
   `/v1/chat/completions` API, so `_call_local_llm` stays one code path. Backend only
   changes defaults, error/fix messages (`server.py`, `doctor.py`), `install.sh`
   steps, and skill hint text.
2. **Default model: Gemma 4 e4b, 4-bit, MLX** (`mlx-community/gemma-4-e4b-it-4bit`).
   Only model to pass all 4 spike tasks on two runs at usable speed; takes ~4–4.5GB
   live. **Documented lighter alternative:** Qwen3.5 4B 4-bit
   (`mlx-community/Qwen3.5-4B-MLX-4bit`, ~3GB) for memory-tight days — it fails
   test-writing consistently, so expect more Claude fixes. Switching is just
   `PEDALPOINT_MODEL`. Benchmarking is not part of the build — ongoing comparison
   comes from `pedalpoint stats` on real work. `mlx_lm.server` keeps
   the model resident — accepted in exchange for no cold starts.
3. **Server writes `.draft` files only.** `local_llm` takes a target path and context
   file paths, reads the context itself, calls the model, writes `<target>.draft`,
   and returns a short summary. Claude reads the draft (cheap input), fixes it if
   needed with Edit, then promotes it with `mv` via Bash (tiny output, goes through
   normal Claude Code permissions, visible to user). The server never writes the real
   file. This replaces the "thin server, never touches files" rule — update `CLAUDE.md`.
4. **Path safety.** The server pins itself to one repo: the git toplevel of its own
   working directory at startup (Claude Code launches the stdio server from the
   session's project dir — builder verifies this; if the cwd is not in a git repo,
   `local_llm` refuses every call with a clear error). Target and all context paths
   must, after resolving `..` and symlinks, fall inside that one repo. The server only
   ever writes paths ending in `.draft`. *(My call — settles "which repo".)*
5. **Inline review.** Structural path no longer spawns a review Agent. Claude reviews
   in the current conversation.
6. **Skip tiny tasks.** Handoff overhead exceeds the work for small edits; Claude
   does those directly.
7. **1–7 score per handoff = what Claude had to do** (drives cost, not code beauty):

   | Score | What Claude did |
   |---|---|
   | 7 | Accepted as-is |
   | 6 | Fixed 1–3 lines |
   | 5 | Several fixes, same file |
   | 4 | Rewrote part |
   | 3 | Rewrote most |
   | 2 | Started over, draft helped |
   | 1 | Started over, draft useless |

8. **Metrics use real transcript token counts**, falling back to estimates if the
   transcript can't be read. `pedalpoint stats` reports net tokens saved, average
   score, redo rate, per model and per week.

## Design detail

### Config (`config.py`)

Add `backend: str` (env `PEDALPOINT_BACKEND`). Backend picks defaults for
`base_url` and `model` when their env vars are unset:

| backend | default base_url | default model |
|---|---|---|
| `mlx` | `http://localhost:8080/v1` | `mlx-community/gemma-4-e4b-it-4bit` |
| `ollama` | `http://localhost:11434/v1` | `gemma4:12b` |

Default backend: `mlx` on macOS arm64, `ollama` otherwise. Invalid backend → `doctor` FAIL.

### Thinking mode

Qwen3.5 and Gemma 4 are reasoning-capable; thinking wastes time and local tokens on
code-gen. Requests must disable it. On MLX: request body
`"chat_template_kwargs": {"enable_thinking": false}` (verified working with
mlx-lm 0.32 in the spike). On Ollama: builder verifies the mechanism for the
OpenAI-compat endpoint (or uses native `/api/chat` with `"think": false`). Also strip
any `<think>…</think>` block and markdown code fences from output before writing.

### `local_llm` tool (new signature)

```
local_llm(
    task: str,                    # instruction, written by Claude — keep short
    target_path: str,             # file to create or replace; server writes <target_path>.draft
    context_paths: list[str] = [],# "path" or "path:START-END" (1-indexed, inclusive)
    system: str | None = None,
    model: str | None = None,
) -> str  # JSON summary
```

- Server builds the prompt: context excerpts (labeled with path + lines), then the
  existing target file contents if it exists (so the model outputs the full updated
  file), then the task. Same "Output only code" system default as today.
- Enforce `context_limit` on the assembled prompt; over limit → ValueError with a
  message the skill treats as "escalate to Agent".
- **Existing-file edits** are allowed only when the target is ≤ ~300 lines (the model
  regenerates the whole file; bigger files waste local time and risk silent damage).
  Over the limit → ValueError the skill treats as "Claude does it directly".
  *(My call.)*
- Writes `<target_path>.draft` (overwrite allowed for `.draft`).
- Computes **changed tokens**: for a new file, the draft's token count; for an
  existing file, tokens in added/changed lines of a line diff (original vs draft).
  Approximation (e.g. chars/4) is fine. This — not `completion_tokens` — is what
  Claude would otherwise have written.
- Returns JSON: `{"handoff_id", "draft_path", "lines", "lines_changed",
  "changed_tokens", "prompt_tokens", "completion_tokens", "seconds", "model",
  "backend"}`. Token counts come from the response `usage` field (0 if absent).
- Appends one record (same fields + timestamp + repo root) to
  `~/.pedalpoint/handoffs.jsonl`.
- The old "return the code as a string" behavior is removed; the skill is the only consumer.

### `record_outcome` tool (new)

```
record_outcome(handoff_id: str, score: int, note: str = "") -> str
```

Appends `{handoff_id, score, note, timestamp}` to `~/.pedalpoint/handoffs.jsonl`.
Validates score 1–7. The skill calls it once per handoff after the draft is promoted
(or abandoned). Its position in the transcript also marks the end of the review window
for stats.

### Skill changes (`skills/route-tasks/SKILL.md`)

- Context Courier still greps first, but passes **paths/line ranges** to `local_llm`
  instead of pasting excerpts into the prompt.
- Before handing off, skip tasks whose expected **lines changed** (not file size) is
  small — **my call: under ~30 lines** — Claude just does them.
- Mechanical and structural paths converge: call `local_llm` → Read the `.draft`
  → fix with Edit if needed → `mv <target>.draft <target>` → run tests → trivial
  failures fixed inline, else escalate → `record_outcome` with the 1–7 score → commit.
- Structural path drops the review Agent; Claude reviews inline. A draft that is
  "a judgment task in disguise" → delete draft, `record_outcome(score=1)`, judgment path.
- Error dispatch tables and backend hint text updated for MLX (`mlx_lm.server`)
  vs Ollama (`ollama serve`). Circuit state transitions (closed / api_fallback /
  open, 402 vs 429, backoff) unchanged.

**Circuit states × new flow** *(my calls)*:

| Circuit | Routing |
|---|---|
| closed | New flow above: skip rule, `local_llm` draft, inline review, `record_outcome`. |
| api_fallback | `claude_api` gets the same draft-writing signature as `local_llm` (`task`, `target_path`, `context_paths`) and writes `.draft` too — otherwise Claude re-types its output, the same waste. Logged to `handoffs.jsonl` with `backend: "claude_api"`. Inline review + `record_outcome` as usual. |
| open | Claude's quota is exhausted, so no review: `local_llm` draft → `mv` → tests → commit flagged `[unreviewed]`, logged to `fallback-log.md` as today, `record_outcome` skipped (stats counts these as "unscored"). Skip rule off. Post-session review kept. |

- **Delete** error tables for the structural review Agent and `claude_api` review
  (that review step no longer exists). Keep the `[unreviewed]` / HIGH PRIORITY
  fallback-log entries only for the OPEN row above.
- **Modes:** `local-only` → skip rule off, always hand off (except judgment tasks);
  `passthrough` → never hand off; `hybrid` → as described.

### `pedalpoint stats` (new CLI subcommand, new module)

`pedalpoint stats [--days N]` (default 7).

1. Read `~/.pedalpoint/handoffs.jsonl`; join call + outcome records by `handoff_id`.
2. For each handoff, locate the Claude Code transcript under `~/.claude/projects/*/`
   containing a tool_result with that `handoff_id`. From the transcript:
   - **call cost** = output tokens of the assistant message that issued `local_llm`.
   - **review cost** = sum of usage (output, and separately input/cache-read) for
     assistant messages after that tool_result, up to and including the one that
     calls `record_outcome` for that `handoff_id`.
3. **Avoided** = `changed_tokens` — the output Claude would have written itself
   doing the task directly. No quality discount here: the measured review cost
   already includes every fix and rewrite, so discounting again would double-count.
4. **Net output saved** = avoided − call cost output − review cost output.
   Input overhead reported separately (cheaper and mostly cached; don't fake a
   combined weighting). A score-1 handoff naturally goes negative (Claude rewrote
   everything *and* paid for the call).
5. If the transcript isn't found or can't be parsed, estimate instead and mark the
   row "estimated": call cost ≈ 100 tokens; review cost ≈
   `changed_tokens × rewrite_share(score)` with **my call, tunable constants**
   7→0.0, 6→0.1, 5→0.3, 4→0.5, 3→0.75, 2→0.9, 1→1.0.
6. Output: per model per week — handoffs, avg score, redo rate (score ≤ 2), local
   tokens, net output saved, input overhead, % estimated. Plain text table.
   Flag a model whose avg score is < 5 or net saved ≤ 0 ("not paying off").

### `doctor`

- New check: backend valid.
- Reachability/model checks: messages and fixes per backend (`mlx_lm.server --model <m>`
  vs `ollama serve` / `ollama pull <m>`). MLX `/v1/models` lists the loaded model;
  builder confirms the id format matches `cfg.model`.

### Running the MLX server

**My call:** pedalpoint does not auto-start `mlx_lm.server`. `install.sh` (when
backend is mlx) installs `mlx-lm` via `uv tool install mlx-lm`, downloads the model
(`hf download`), and prints the start command. `doctor` points at the same command
when unreachable. A launchd agent is a possible later addition, not in scope.

### `install.sh`

Backend-aware: `--backend mlx|ollama` flag (default per platform as above). MLX path
skips all `ollama` steps. Registers `PEDALPOINT_BACKEND` in the MCP config env.

### Migration and version skew *(my calls)*

- **Backend inference:** if `PEDALPOINT_BACKEND` is unset but `PEDALPOINT_BASE_URL`
  is set, infer `ollama` when the URL uses port 11434, else `mlx`. Existing installs
  (which register base_url + gemma4:12b explicitly) keep working as Ollama unchanged.
- **Switching** is done by re-running `install.sh --backend mlx`, which overwrites the
  pedalpoint MCP env (it already re-registers the server).
- **Skill pinning:** `install.sh` fetches `SKILL.md` from the release tag matching the
  installed package version, not `main`. `local_llm`'s summary JSON includes
  `"server_version"`; the skill warns if it's missing (old server) and tells the user
  to re-run `install.sh`.
- Release as v0.4.0 (breaking tool signature).

### Docs

Update `CLAUDE.md` (key design decisions, file responsibilities, state/log files,
gotchas) and `README.md` for the backend choice, draft-writing server, and `stats`.

## Left to the builder

- Module boundaries (e.g. a `paths.py` for safety checks, `stats.py`, `handoff_log.py`).
- Exact prompt assembly format.
- Exact JSON field names beyond those listed, as long as skill and stats agree.
- How tests fake transcripts and backends.
- Coverage targets for new modules — follow the existing bar (server ≥90%; pure
  modules like path safety and stats math aim for 100%).

## Appendix: spike results (2026-10-26, M4 Air 16GB, normal apps open)

Four auto-graded pedalpoint-style tasks (add Config field, write a doctor check,
write pytest tests that must catch a mutant, implement a stats function). Thinking off.

| Model | Backend | Passed (run 1 / run 2) | Speed | Cold load | Weights on disk | Notes |
|---|---|---|---|---|---|---|
| gemma4:12b | Ollama | 4/4 | 9.5 tok/s | 15–41s | 7.6GB | Available RAM 8.3 → 0.8GB |
| **gemma-4-e4b-it-4bit** | MLX | **4/4 · 4/4** | 25–28 tok/s | ~5s | 5.2GB | ~4–4.5GB live; ≤0.2GB swap growth |
| Qwen3.5-4B-MLX-4bit | MLX | 3/4 · 3/4 | 29 tok/s | 3.5–6.6s | 3.0GB | Fails test-writing both runs (missing import; broken parametrize) |
| Qwen3.5-4B-OptiQ-4bit | MLX | 3/4 | 22 tok/s | 4.1s | 4.0GB | Same test-writing failure |
| gemma-4-E4B-it-qat-4bit | MLX | 4/4 | 18 tok/s | 7.4s | 6.8GB | +2.2GB swap |
| gemma-4-e2b-it-4bit | MLX | 2/4 | 54 tok/s | 5.2s | 3.6GB | Weak tests + logic bug |

Memory readings are system-wide (GPU memory isn't visible in process RSS on Apple
Silicon) and noisy, since other apps were running.

Spike harness: throwaway, in session scratchpad; not part of the repo.
