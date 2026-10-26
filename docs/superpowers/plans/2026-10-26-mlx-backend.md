# MLX Backend + Draft-Writing Server + Savings Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let pedalpoint run a small MLX model (default Gemma 4 e4b) alongside Ollama, have the server write `.draft` files so Claude never re-types local output, and add `pedalpoint stats` measuring real net Claude tokens saved.

**Architecture:** Backend is a config setting that only changes defaults, hint text and a per-backend "thinking off" request field; both backends use the same OpenAI-style client. A shared `_create_draft` core (used by `local_llm` and `claude_api`) reads context files, calls the model, writes `<target>.draft` inside the pinned repo, and logs to `~/.pedalpoint/handoffs.jsonl`. `pedalpoint stats` joins that log with Claude Code transcripts for real review costs.

**Tech Stack:** Python ≥3.11, FastMCP, httpx, anthropic SDK, pytest + respx + pytest-asyncio, bats for install.sh, mlx-lm (user-installed, not a package dependency).

**Spec:** `docs/superpowers/specs/2026-10-26-mlx-backend-design.md`

## Global Constraints

- Branch: all work on `feat/mlx-backend`; Conventional Commits; commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- TDD per task: failing test → confirm fail → implement → confirm pass → commit.
- Coverage: `circuit_breaker.py` = 100%, `error_classifier.py` = 100%, `server.py` ≥ 90%; new pure modules (`paths.py`, `drafting.py`, `stats.py`) = 100%; overall `--cov-fail-under=90`.
- Backends: exactly `"mlx"` and `"ollama"`.
- Defaults — mlx: base_url `http://localhost:8080/v1`, model `mlx-community/gemma-4-e4b-it-4bit`; ollama: base_url `http://localhost:11434/v1`, model `gemma4:12b`.
- Default backend: `mlx` on macOS arm64, else `ollama`; if `PEDALPOINT_BACKEND` unset and `PEDALPOINT_BASE_URL` set → `ollama` when URL contains `:11434`, else `mlx`.
- Server writes only paths ending `.draft`, only inside the repo pinned at startup.
- Existing-file regeneration limit: 300 lines. Skill skip threshold: < ~30 lines changed.
- Handoff log: `~/.pedalpoint/handoffs.jsonl`. Server never touches `~/.pedalpoint/state.json`.
- Score scale 1–7. Estimate-mode constants: call cost 100 tokens; `REWRITE_SHARE = {7: 0.0, 6: 0.1, 5: 0.3, 4: 0.5, 3: 0.75, 2: 0.9, 1: 1.0}`.
- Token estimate for text: `ceil(len(text) / 4)`.
- `get_config()` is `lru_cache`d — tests call `get_config.cache_clear()` before and after env monkeypatching.
- Release version: `0.4.0`.

## Review Focus

1. A path inside the repo that is (or traverses) a symlink pointing outside the repo → refused, same as `../`. (Task 2)
2. Model returns empty output, or only prose with no code → no draft written; ValueError "Model returned empty output". (Task 5)
3. New file in a directory that doesn't exist yet (`src/pkg/new/mod.py`) → parent dirs created inside the repo, draft written. (Task 5)
4. One Claude API response split across several transcript lines sharing a `requestId` → its usage counted once, not per line. (Task 8)
5. `handoffs.jsonl` with a truncated/corrupt line (crash mid-write) → stats skips the line and still reports. (Task 4)

---

### Task 1: Backend-aware config and backend helpers

**Files:**
- Modify: `src/pedalpoint/config.py`
- Create: `src/pedalpoint/backends.py`
- Test: `tests/unit/test_config.py`, `tests/unit/test_backends.py` (create)
- Modify: every `Config(...)` construction in `tests/unit/*.py` and `tests/integration/*.py` (add `backend=`)

**Interfaces:**
- Produces:
  - `Config.backend: str` (field placed right after `model`)
  - `config._platform_default_backend() -> str` (module-level; tests monkeypatch it)
  - `backends.BACKENDS: tuple[str, ...] = ("mlx", "ollama")`
  - `backends.start_hint(cfg: Config) -> str` — mlx: `f"mlx_lm.server --model {cfg.model}"`; ollama: `"ollama serve"`
  - `backends.pull_hint(cfg: Config, model: str) -> str` — mlx: `f"uvx --from huggingface_hub hf download {model}"`; ollama: `f"ollama pull {model}"`
  - `backends.extra_body(cfg: Config) -> dict` — mlx: `{"chat_template_kwargs": {"enable_thinking": False}}`; ollama: `{"reasoning_effort": "none"}`; other: `{}`
  - `backends.label(cfg: Config) -> str` — `"MLX"` / `"Ollama"` / `cfg.backend`

- [ ] **Step 1: Write failing tests** in `tests/unit/test_config.py`:
  - `test_defaults` → rename to `test_defaults_ollama`: monkeypatch `pedalpoint.config._platform_default_backend` to return `"ollama"`, clear env (add `PEDALPOINT_BACKEND` to the cleared list); assert existing values plus `cfg.backend == "ollama"`.
  - `test_defaults_mlx`: platform default `"mlx"`, env cleared → `backend == "mlx"`, `base_url == "http://localhost:8080/v1"`, `model == "mlx-community/gemma-4-e4b-it-4bit"`.
  - `test_backend_inferred_from_ollama_url`: platform `"mlx"`, `PEDALPOINT_BASE_URL=http://localhost:11434/v1` → `backend == "ollama"`, `model == "gemma4:12b"`.
  - `test_backend_inferred_from_other_url`: platform `"ollama"`, `PEDALPOINT_BASE_URL=http://localhost:9000/v1` → `backend == "mlx"`.
  - `test_explicit_backend_wins`: `PEDALPOINT_BACKEND=ollama`, `PEDALPOINT_BASE_URL=http://localhost:8080/v1` → `backend == "ollama"`, `base_url` unchanged.
  - `test_platform_default`: monkeypatch `platform.system`/`platform.machine` → (`"Darwin"`, `"arm64"`) gives `"mlx"`; (`"Linux"`, `"x86_64"`) gives `"ollama"`.

  In `tests/unit/test_backends.py`: one test per function per backend asserting the exact strings/dicts above, plus `extra_body` for an unknown backend returns `{}`.

- [ ] **Step 2: Run** `pytest tests/unit/test_config.py tests/unit/test_backends.py -v` — Expected: FAIL (`backend` attribute / module missing).
- [ ] **Step 3: Implement** `Config.backend`, `_platform_default_backend()` (uses `platform.system()`/`platform.machine()`), resolution order from Global Constraints, then `backends.py`. Add `backend=` to every test `Config(...)` literal.
- [ ] **Step 4: Run** `pytest tests/unit/ -q` — Expected: all PASS.
- [ ] **Step 5: Commit** `feat: add backend setting with mlx and ollama defaults`

---

### Task 2: Repo path safety

**Files:**
- Create: `src/pedalpoint/paths.py`
- Test: `tests/unit/test_paths.py`

**Interfaces:**
- Produces:
  - `find_repo_root(start: Path) -> Path | None` — walk up from `start.resolve()` to the first dir containing `.git` (dir or file, so worktrees work); `None` if none.
  - `resolve_in_repo(raw: str, root: Path) -> Path` — relative paths resolve against `root`; result `.resolve()`d (follows symlinks); raises `ValueError(f"Path {raw!r} is outside the project repo {root}")` unless `root.resolve()` is the path or one of its parents.
  - `parse_context_spec(spec: str) -> tuple[str, int | None, int | None]` — `"a.py"` → `("a.py", None, None)`; `"a.py:10-40"` → `("a.py", 10, 40)`; bad range (`"a.py:40-10"`, `"a.py:x-3"`, `"a.py:0-3"`) → `ValueError`. Only a trailing `:N-M` is treated as a range.
  - `draft_path_for(target: Path) -> Path` — `target.with_name(target.name + ".draft")`.

- [ ] **Step 1: Write failing tests** (use `tmp_path` with a `.git` dir):
  - `test_find_repo_root_from_nested_dir`, `test_find_repo_root_git_file_worktree`, `test_find_repo_root_none`.
  - `test_resolve_relative_inside`, `test_resolve_absolute_inside`.
  - `test_resolve_dotdot_outside_raises` — `"../x.py"` → `ValueError`, message contains `"outside the project repo"`.
  - `test_resolve_absolute_other_repo_raises`.
  - `test_resolve_symlink_escaping_repo_raises` — `root/link -> tmp_path/"outside"`; `"link/x.py"` raises. *(Review Focus 1)*
  - `test_parse_context_spec_*` for the cases above.
  - `test_draft_path_for` — `Path("a/b.py")` → `Path("a/b.py.draft")`.
- [ ] **Step 2: Run** `pytest tests/unit/test_paths.py -v` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `paths.py`.
- [ ] **Step 4: Run** `pytest tests/unit/test_paths.py -v --cov=pedalpoint.paths --cov-report=term-missing` — Expected: PASS, 100%.
- [ ] **Step 5: Commit** `feat: add repo-pinned path safety helpers`

---

### Task 3: Draft prompt assembly, output cleanup, change sizing

**Files:**
- Create: `src/pedalpoint/drafting.py`
- Test: `tests/unit/test_drafting.py`

**Interfaces:**
- Produces:
  - `MAX_EDIT_LINES = 300`
  - `estimate_tokens(text: str) -> int` — `ceil(len(text) / 4)`
  - `strip_output(text: str) -> str` — remove all `<think>…</think>` blocks (DOTALL); if fenced code blocks exist return the longest block's contents, else the stripped text; always ends with exactly one `\n` unless empty (then `""`).
  - `build_prompt(task: str, context: list[tuple[str, str]], target_rel: str, existing: str | None) -> str` — `context` items are `(label, text)` where label is `"path"` or `"path lines N-M"`. Sections in order: `## Context: <label>` + fenced text per item; `## Current contents of <target_rel>` + fenced text if `existing` is not None; `## Task` + task + final line `Output the complete contents of <target_rel>.`
  - `change_size(original: str | None, draft: str) -> tuple[int, int]` — returns `(lines_changed, changed_tokens)`. New file (`original is None`): all draft lines, `estimate_tokens(draft)`. Existing: via `difflib.ndiff`/`unified_diff`, lines added or replaced in the draft (`+` lines), and `estimate_tokens` of those lines joined with `\n`.

- [ ] **Step 1: Write failing tests:**
  - `test_strip_output_removes_think_and_fence`: `"<think>x</think>\n```python\nprint(1)\n```"` → `"print(1)\n"`.
  - `test_strip_output_longest_fence_wins`, `test_strip_output_plain_text`, `test_strip_output_empty` (`"<think>a</think>"` → `""`).
  - `test_build_prompt_order`: assert `index("## Context: a.py lines 1-3") < index("## Current contents of t.py") < index("## Task")` and ends with `"Output the complete contents of t.py."`.
  - `test_build_prompt_new_file_has_no_current_section`.
  - `test_change_size_new_file`: `"a\nb\n"` → `(2, estimate_tokens("a\nb\n"))`.
  - `test_change_size_edit_counts_only_changed`: 100-line original, draft adds 2 lines → `lines_changed == 2`.
  - `test_change_size_identical` → `(0, 0)`.
  - `test_estimate_tokens`: `"abcde"` → `2`.
- [ ] **Step 2: Run** `pytest tests/unit/test_drafting.py -v` — Expected: FAIL.
- [ ] **Step 3: Implement** `drafting.py`.
- [ ] **Step 4: Run** with `--cov=pedalpoint.drafting` — Expected: PASS, 100%.
- [ ] **Step 5: Commit** `feat: add draft prompt assembly and change sizing`

---

### Task 4: Handoff log

**Files:**
- Create: `src/pedalpoint/handoff_log.py`
- Test: `tests/unit/test_handoff_log.py`

**Interfaces:**
- Produces:
  - `log_path() -> Path` — `Path.home() / ".pedalpoint" / "handoffs.jsonl"`
  - `append(record: dict, path: Path | None = None) -> None` — creates parent dir; writes `json.dumps(record) + "\n"` in append mode.
  - `read_all(path: Path | None = None) -> list[dict]` — missing file → `[]`; skips blank and unparseable lines.
  - Record shapes (consumers: Tasks 5, 6, 9):
    - call: `{"kind": "call", "handoff_id", "ts" (ISO UTC), "repo", "backend", "model", "target", "draft_path", "lines", "lines_changed", "changed_tokens", "prompt_tokens", "completion_tokens", "seconds"}`
    - outcome: `{"kind": "outcome", "handoff_id", "ts", "score" (int 1–7), "note"}`

- [ ] **Step 1: Write failing tests:** `test_append_creates_dir_and_appends`, `test_read_all_missing_file_empty`, `test_read_all_skips_corrupt_line` (write a valid line, `{"kind": "ca`, a valid line → 2 records) *(Review Focus 5)*, `test_log_path_under_home` (monkeypatch `HOME`).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS, 100%.
- [ ] **Step 5: Commit** `feat: add handoff jsonl log`

---

### Task 5: `local_llm` writes drafts

**Files:**
- Modify: `src/pedalpoint/server.py`
- Test: `tests/unit/test_server.py`, `tests/integration/test_ollama.py` (update to new return type)

**Interfaces:**
- Consumes: Task 1 `backends.*`, Task 2 `paths.*`, Task 3 `drafting.*`, Task 4 `handoff_log.append`.
- Produces:
  - `_call_local_llm(client, prompt: str, system: str | None, model: str, cfg: Config) -> tuple[str, dict]` — returns `(content, usage)`; `usage` is the response's `usage` dict or `{}`. Request JSON = `{"model", "messages"} | backends.extra_body(cfg)`. Error messages use `backends.label(cfg)`, `backends.start_hint(cfg)`, `backends.pull_hint(cfg, model)` instead of hard-coded Ollama text; keep the existing wording shape (`"<Label> not reachable at <url> — is it running? Start: <hint>"`, `"Model `<m>` not found — run: <pull_hint>"`).
  - `Generate = Callable[[str, str], Awaitable[tuple[str, int, int]]]` — `(prompt, system) -> (text, prompt_tokens, completion_tokens)`
  - `async def _create_draft(generate: Generate, *, task: str, target_path: str, context_paths: list[str], system: str, repo_root: Path | None, backend: str, model: str, cfg: Config) -> dict`
  - `local_llm(ctx, task: str, target_path: str, context_paths: list[str] | None = None, system: str | None = None, model: str | None = None) -> str` — JSON string of the dict below.
  - Return dict: `{"handoff_id", "draft_path", "lines", "lines_changed", "changed_tokens", "prompt_tokens", "completion_tokens", "seconds", "model", "backend", "server_version"}` (`server_version` from `importlib.metadata.version("pedalpoint")`).
  - Lifespan context gains `"repo_root": paths.find_repo_root(Path.cwd())`; startup warning uses backend label + start hint.

`local_llm` adapts `_call_local_llm` to `Generate` with a closure mapping `usage.get("prompt_tokens", 0)` / `usage.get("completion_tokens", 0)`.

`_create_draft` order: `repo_root is None` → `ValueError("Not in a git repository — local_llm needs a project repo")`; resolve target + each context path via `resolve_in_repo`; read context slices (1-indexed inclusive); existing target with > `MAX_EDIT_LINES` lines → `ValueError(f"Target has {n} lines (> 300) — too large for local regeneration; edit directly")`; `build_prompt`; `estimate_tokens(prompt) > cfg.context_limit` → `ValueError(f"Context too large: ~{n} tokens > limit {limit} — escalate to Agent")`; call `generate`; `strip_output`; empty → `ValueError("Model returned empty output")`; `mkdir(parents=True)` for the draft's parent; write draft; `change_size`; `handoff_log.append` call record; return dict. `handoff_id = uuid4().hex[:12]`.

- [ ] **Step 1: Write failing tests** (respx-mock the chat endpoint; `tmp_path` repo with `.git`; monkeypatch `HOME` to `tmp_path/"home"`):
  - Update existing `_call_local_llm` tests to unpack `(text, usage)`.
  - `test_call_local_llm_sends_mlx_thinking_off` / `..._ollama_reasoning_none`: inspect request JSON for the `extra_body` keys.
  - `test_call_local_llm_errors_use_backend_hints`: mlx config, ConnectError → message contains `"MLX"` and `"mlx_lm.server"`; 404 → contains `"hf download"`.
  - `test_create_draft_new_file`: writes `src/new.py.draft` with stripped output; returned `lines_changed == lines`; real `src/new.py` not created; one call record in `handoffs.jsonl`.
  - `test_create_draft_creates_parent_dirs` — target `src/pkg/new/mod.py`. *(Review Focus 3)*
  - `test_create_draft_edit_existing_counts_changes` — 50-line file, model returns it + 2 lines → `lines_changed == 2`.
  - `test_create_draft_context_slice_in_prompt` — `context_paths=["a.py:2-3"]`; captured prompt contains lines 2–3 only.
  - `test_create_draft_outside_repo_raises`, `test_create_draft_no_repo_raises`, `test_create_draft_too_many_lines_raises` (301 lines), `test_create_draft_context_too_large_raises` (tiny `context_limit`).
  - `test_create_draft_empty_output_raises_and_writes_nothing` — model returns `"<think>hm</think>"`; no `.draft` file, no log record. *(Review Focus 2)*
  - `test_local_llm_tool_returns_json` — via a fake ctx (pattern of existing tool tests); parse JSON, keys match the return dict.
- [ ] **Step 2: Run** `pytest tests/unit/test_server.py -v` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** in `server.py`.
- [ ] **Step 4: Run** `pytest tests/unit/ --cov=pedalpoint --cov-report=term-missing` — Expected: PASS, `server.py` ≥ 90%.
- [ ] **Step 5: Commit** `feat: local_llm writes .draft files inside the project repo`

---

### Task 6: `claude_api` drafts, `record_outcome`, `local_llm_status`

**Files:**
- Modify: `src/pedalpoint/server.py`
- Test: `tests/unit/test_server.py`

**Interfaces:**
- Consumes: Task 5 `_create_draft`, `Generate`; Task 4 `handoff_log.append`.
- Produces:
  - `_call_claude_api(prompt: str, system: str, cfg: Config) -> tuple[str, int, int]` — `(text, usage.input_tokens, usage.output_tokens)`; existing error behavior unchanged (including `"ANTHROPIC_API_KEY not set..."`).
  - `claude_api(ctx, task: str, target_path: str, context_paths: list[str] | None = None, system: str = "") -> str` — same JSON as `local_llm`, `backend="claude_api"`, `model=cfg.api_model`.
  - `record_outcome(ctx, handoff_id: str, score: int, note: str = "") -> str` — score outside 1–7 → `ValueError("score must be 1-7")`; appends outcome record; returns `"recorded"`.
  - `local_llm_status(ctx) -> str` — JSON `{"backend", "model", "base_url", "reachable": bool, "repo_root": str | None, "server_version"}`; reachable = GET `/models` returns 200 within 5s. The skill's prerequisite probe uses this instead of `local_llm("ping")`.

- [ ] **Step 1: Write failing tests:** `test_claude_api_writes_draft` (patch `anthropic.AsyncAnthropic`; check `backend == "claude_api"`, draft exists), update existing `_call_claude_api` tests to the tuple return, `test_record_outcome_appends`, `test_record_outcome_rejects_0_and_8`, `test_local_llm_status_reachable` / `_unreachable` (respx).
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/unit/ --cov=pedalpoint --cov-report=term-missing` — Expected: PASS, `server.py` ≥ 90%.
- [ ] **Step 5: Commit** `feat: claude_api drafts, record_outcome and status tools`

---

### Task 7: Backend-aware `doctor`

**Files:**
- Modify: `src/pedalpoint/doctor.py`
- Test: `tests/unit/test_doctor.py`

**Interfaces:**
- Consumes: Task 1 `backends.*`.
- Produces: `check_backend(cfg: Config) -> CheckResult` — PASS `f"Backend: {cfg.backend}"` / FAIL `f"Unknown backend {cfg.backend!r}"` with fix `"export PEDALPOINT_BACKEND=mlx"`. Rename `check_ollama_reachable` → `check_server_reachable` (messages/fixes via `backends.label` / `start_hint`); `check_model_available` fix via `pull_hint`, and for mlx adds to the fix: `then restart: <start_hint>`. `run_all` order: binary, backend, server reachable, model, pedalpoint dir, API key.

- [ ] **Step 1: Write failing tests:** `check_backend` pass/fail; reachability FAIL message for mlx contains `"MLX not reachable"` and fix `"mlx_lm.server --model mlx-community/gemma-4-e4b-it-4bit"`; ollama variant keeps `"ollama serve"`; model-missing fix per backend; `run_all` returns 6 results in the order above. Update existing tests for the rename.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.** Builder check: confirm against a running `mlx_lm.server` that `/v1/models` lists the model under the same id as `cfg.model`; if it lists cached repos differently, match on that id format and note it in a code comment.
- [ ] **Step 4: Run** `pytest tests/unit/test_doctor.py -v` — Expected: PASS.
- [ ] **Step 5: Commit** `feat: backend-aware doctor checks`

---

### Task 8: Transcript cost extraction

**Files:**
- Create: `src/pedalpoint/transcripts.py`
- Test: `tests/unit/test_transcripts.py` (build small fake `.jsonl` files in `tmp_path`)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class HandoffCost: call_output: int; review_output: int; review_input: int; complete: bool`
  - `projects_dir() -> Path` — `Path.home() / ".claude" / "projects"`
  - `handoff_costs(handoff_ids: set[str], root: Path | None = None) -> dict[str, HandoffCost]` — scans `root/*/*.jsonl`; never raises on bad files/lines (skip them).

Algorithm (per transcript file, lines in order):
```
seen_requests = set(); open = {}            # handoff_id -> running HandoffCost fields
pending_calls = {}                          # tool_use_id -> output tokens of issuing request
for entry in lines:
  if entry.type == "assistant":
      req = entry.requestId or entry.uuid; usage = entry.message.usage or {}
      first_time = req not in seen_requests; seen_requests.add(req)
      out = usage.output_tokens; inp = input_tokens + cache_read_input_tokens + cache_creation_input_tokens
      if first_time: add out/inp to every open handoff's review totals
      for tool_use in entry.message.content:
          name ends with "__local_llm" or "__claude_api": pending_calls[tool_use.id] = out
          name ends with "__record_outcome" and input.handoff_id in open:
              close it (complete=True)  # this request's usage was already added above
  if entry.type == "user":
      for tool_result in entry.message.content:
          if tool_use_id in pending_calls: find any wanted handoff_id substring in its text
              → open[hid] = {call_output: pending_calls[id], review_output: 0, review_input: 0}
at EOF: remaining open → complete=False
```
Usage is counted once per `requestId` even when one response is split across several lines.

- [ ] **Step 1: Write failing tests:**
  - `test_single_handoff_costs` — call request (output 80) → tool_result with id → two review requests (output 40, 30; input 1000 each) → record_outcome request (output 20) → `HandoffCost(80, 90, 3000+…, True)` (assert exact numbers you construct).
  - `test_split_request_counted_once` — same `requestId` on two assistant lines → counted once. *(Review Focus 4)*
  - `test_unclosed_handoff_incomplete`, `test_unknown_ids_ignored`, `test_corrupt_line_skipped`, `test_missing_projects_dir_empty`.
  - `test_two_overlapping_handoffs` — both open → shared review requests count toward both.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** with `--cov=pedalpoint.transcripts` — Expected: PASS, ≥ 95%.
- [ ] **Step 5: Commit** `feat: extract per-handoff Claude costs from transcripts`

---

### Task 9: `pedalpoint stats` and `--version`

**Files:**
- Create: `src/pedalpoint/stats.py`
- Modify: `src/pedalpoint/cli.py`
- Test: `tests/unit/test_stats.py`, `tests/unit/test_cli.py` (create if absent)

**Interfaces:**
- Consumes: Task 4 `handoff_log.read_all`, Task 8 `handoff_costs`, `HandoffCost`.
- Produces:
  - `ESTIMATED_CALL_COST = 100`, `REWRITE_SHARE` (Global Constraints)
  - `@dataclass(frozen=True) class Handoff: handoff_id: str; ts: datetime; model: str; backend: str; completion_tokens: int; changed_tokens: int; score: int | None`
  - `join_records(records: list[dict]) -> list[Handoff]` — call records joined with the latest outcome per id; outcomes without a call ignored.
  - `net_saved(h: Handoff, cost: HandoffCost | None) -> tuple[int, int, bool]` — `(net_output, input_overhead, estimated)`. Measured (`cost` not None and `cost.complete`): `changed_tokens - call_output - review_output`, `review_input`, `False`. Otherwise estimated: `changed_tokens - 100 - round(changed_tokens * REWRITE_SHARE[score])` (score None → share 0), input `0`, `True`.
  - `@dataclass(frozen=True) class Row: model: str; week: str  # "2026-W44"; handoffs: int; unscored: int; avg_score: float | None; redo_rate: float | None; local_tokens: int; net_output: int; input_overhead: int; pct_estimated: float; paying_off: bool`
  - `summarize(handoffs: list[Handoff], costs: dict[str, HandoffCost], now: datetime, days: int) -> list[Row]` — filter `ts >= now - days`; group by `(model, ISO week)`; `redo_rate` = share of scored with score ≤ 2; `paying_off = net_output > 0 and (avg_score is None or avg_score >= 5)`.
  - `format_rows(rows: list[Row]) -> str` — plain-text table; columns: model, week, handoffs, avg score, redo %, local tok, net saved, input overhead, est %, and a `NOT PAYING OFF` marker on failing rows; empty → `"No handoffs in the last N days."`
  - CLI: `pedalpoint stats [--days N]` (default 7) prints `format_rows(...)`, exit 0; `pedalpoint --version` prints `pedalpoint <version>`.

- [ ] **Step 1: Write failing tests:**
  - `test_net_saved_measured`: changed 500, cost (80, 120, 4000, True) → `(300, 4000, False)`.
  - `test_net_saved_estimated_score_6`: changed 500, no cost → `500 - 100 - 50 = 350`, estimated.
  - `test_net_saved_score_1_negative`: changed 500, no cost → `-100`.
  - `test_net_saved_incomplete_cost_falls_back`.
  - `test_join_records_latest_outcome_wins`, `test_join_records_orphan_outcome_ignored`.
  - `test_summarize_groups_by_model_and_week`, `test_summarize_filters_by_days`, `test_summarize_flags_low_score` (avg 4 → `paying_off False`), `test_summarize_flags_negative_net`, `test_summarize_unscored_counted`.
  - `test_format_rows_empty`, `test_format_rows_marks_not_paying_off`.
  - CLI: `test_cli_stats_runs` (monkeypatch `HOME` to empty tmp → prints "No handoffs"), `test_cli_version`.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/unit/ --cov=pedalpoint --cov-fail-under=90` — Expected: PASS; `stats.py` 100%.
- [ ] **Step 5: Commit** `feat: add pedalpoint stats for net token savings`

---

### Task 10: Backend-aware `install.sh`

**Files:**
- Modify: `install.sh`
- Test: `tests/install/test_install.bats`

**Interfaces:**
- Consumes: Task 9 `pedalpoint --version`; Task 1 defaults.
- Produces: flags `--backend mlx|ollama` (default: `mlx` when `uname -s` = Darwin and `uname -m` = arm64, else `ollama`), `--model`, `--base-url`; defaults per backend from Global Constraints. MCP registration adds `-e PEDALPOINT_BACKEND=<backend>`. Skill fetched from `https://raw.githubusercontent.com/EMSwank/pedalpoint/v<version>/skills/route-tasks/SKILL.md` where `<version>` comes from `pedalpoint --version` (fall back to `main` with a WARNING if that fails).

MLX path: skip all `ollama` checks/pull; install `mlx-lm` (`uv tool install mlx-lm`, else `pipx install mlx-lm`, else WARNING with the manual command); download the model with `uvx --from huggingface_hub hf download <model>` (WARNING + manual command on failure, not fatal); final summary prints `Start the model server: mlx_lm.server --model <model>`. Ollama path: unchanged behavior.

- [ ] **Step 1: Write failing bats tests** (stub `uname`, `uv`, `uvx`, `pedalpoint` alongside existing stubs):
  - `--backend mlx`: no `ollama` invoked; `uv tool install mlx-lm` invoked; `hf download mlx-community/gemma-4-e4b-it-4bit` invoked; `claude mcp add` args include `PEDALPOINT_BACKEND=mlx` and `PEDALPOINT_BASE_URL=http://localhost:8080/v1`; output contains `mlx_lm.server --model`.
  - default on stubbed Darwin/arm64 → mlx; on stubbed Linux → ollama with existing assertions.
  - `--backend ollama` keeps the current pull/registration assertions plus `PEDALPOINT_BACKEND=ollama`.
  - skill URL contains `/v0.4.0/` when stub `pedalpoint --version` prints `pedalpoint 0.4.0`; contains `/main/` + WARNING when it fails.
  - `--backend foo` → exit 1, `Unknown backend`.
- [ ] **Step 2: Run** `bats tests/install/test_install.bats` — Expected: new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `bats tests/install/test_install.bats` — Expected: all PASS (existing 14 updated where they assumed Ollama on a Darwin host).
- [ ] **Step 5: Commit** `feat: install.sh supports mlx backend and pins skill to release`

---

### Task 11: Rewrite the route-tasks skill

**Files:**
- Modify: `skills/route-tasks/SKILL.md`
- Modify/Create: `tests/skill/scenarios/*.md`

**Interfaces:**
- Consumes: tool signatures from Tasks 5–6 (`local_llm`, `claude_api`, `record_outcome`, `local_llm_status`) and error texts from Task 5.

Required content changes (spec sections "Skill changes" and "Circuit states × new flow"):
- Prerequisites: call `local_llm_status`; not reachable → print `⚠ <backend> unreachable — start it with: <hint>` (MLX: `mlx_lm.server --model <model>`; Ollama: `ollama serve`) and fall back to Agent; missing `server_version` in any tool result → `⚠ pedalpoint server is older than this skill — re-run install.sh`.
- Mode handling: `local-only` → skip rule off; `passthrough` → never hand off; `hybrid` → full flow.
- Step 3 Context Courier: still grep first (empty → escalate rules unchanged), but pass `path:START-END` specs in `context_paths`; never paste excerpts into `task`.
- New skip rule before handoff: expected lines changed < ~30 → Claude does it directly (hybrid only).
- Step 4 unified local path (closed circuit): `local_llm(task, target_path, context_paths)` → Read `<target>.draft` → fix with Edit if needed → `mv <target>.draft <target>` → `pytest tests/ -x -q` (trivial fails fixed inline; non-trivial escalate) → `record_outcome(handoff_id, score, note)` using the 1–7 table → commit. Judgment-in-disguise → `rm` draft, `record_outcome(score=1)`, judgment path.
- api_fallback: same flow with `claude_api`.
- open: `local_llm` → `mv` → tests → commit flagged `[unreviewed]` → fallback-log entry; no `record_outcome`.
- Error table additions (not circuit events, never change state): `outside the project repo`, `Not in a git repository`, `too large for local regeneration`, `Context too large` → Claude does the task directly; `Model returned empty output` → retry once, then Claude does it.
- Delete the structural review Agent and `claude_api` review error tables; keep fallback-log formats only for the open-circuit row; keep Step 5 post-session review.
- Include the 1–7 score table verbatim from the spec.

- [ ] **Step 1: Update scenarios first** (they are the manual tests): rewrite `structural_patch.md` → inline review + score 6; replace `structural_429_retry.md`, `structural_402_fallback.md` (review-agent errors no longer exist) with `draft_open_circuit_unreviewed.md`; add `skip_tiny_task.md`, `draft_outside_repo_escalates.md`, `draft_too_large_escalates.md`, `record_outcome_scoring.md`, `prereq_mlx_unreachable.md`, `api_fallback_claude_api_draft.md`. Same Setup / Input Task / Expected Behavior / Verification format as existing scenarios.
- [ ] **Step 2: Rewrite `SKILL.md`** to satisfy every scenario.
- [ ] **Step 3: Verify** — walk each scenario against the skill text; `grep -n "Agent review\|ollama serve" skills/route-tasks/SKILL.md` shows `ollama serve` only in the Ollama hint and no review-Agent spawn.
- [ ] **Step 4: Commit** `feat: route-tasks uses server-written drafts with inline review and scoring`

---

### Task 12: MLX integration test, docs, version bump

**Files:**
- Create: `tests/integration/test_mlx.py`
- Modify: `pyproject.toml` (version `0.4.0`; add marker text "live Ollama or MLX"), `CLAUDE.md`, `README.md`

- [ ] **Step 1: Write `tests/integration/test_mlx.py`** (skipped unless `PEDALPOINT_INTEGRATION=true` and `PEDALPOINT_BACKEND=mlx`): one test that runs `_create_draft` with the real `_call_local_llm` against a running `mlx_lm.server` into a `tmp_path` repo for a small "write a function" task; asserts draft exists, parses with `ast.parse`, contains no `<think>`, and `completion_tokens > 0`.
- [ ] **Step 2: Run** with `mlx_lm.server --model mlx-community/gemma-4-e4b-it-4bit` up: `PEDALPOINT_INTEGRATION=true PEDALPOINT_BACKEND=mlx pytest tests/integration/test_mlx.py -v` — Expected: PASS. Also run the Ollama integration test if Ollama is available, to confirm `reasoning_effort: "none"` is accepted (if Ollama rejects it, switch `extra_body` for ollama to `{}` and rely on `strip_output`; note it in `backends.py`).
- [ ] **Step 3: Update docs:**
  - `CLAUDE.md`: replace "Thin server, smart skill" with the draft-writing rule (server reads context, writes only `.draft` inside the pinned repo, never touches `state.json`); file-responsibilities rows for `backends.py`, `paths.py`, `drafting.py`, `handoff_log.py`, `transcripts.py`, `stats.py`; `handoffs.jsonl` format; gotchas: backend inference from base_url, `_platform_default_backend` monkeypatching, integration commands for MLX.
  - `README.md`: backend choice and `--backend`, starting `mlx_lm.server`, model options (e4b default; Qwen3.5 4B lighter; numbers from the spec appendix), `pedalpoint stats`.
- [ ] **Step 4: Full verification:** `pytest tests/unit/ --cov=pedalpoint --cov-fail-under=90` and `bats tests/install/test_install.bats` and `ruff check src tests` — Expected: all pass; coverage targets from Global Constraints met.
- [ ] **Step 5: Commit** `chore: bump version to 0.4.0, document mlx backend and stats`
