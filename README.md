# pedalpoint

Route mechanical development tasks to a local LLM (MLX on Apple Silicon, or Ollama) via Claude Code, so your Claude session goes further. Automatically falls back to local-only mode when Claude quota is exhausted.

## What it does

- **Hybrid routing:** Claude classifies each task. Mechanical work (scaffolding, CRUD, test stubs) goes to your local LLM. Judgment work (architecture, debugging, integration) stays with Claude.
- **Three-tier quota fallback:** When Claude Pro returns a quota error, pedalpoint first routes judgment and structural tasks to Claude API (pay-per-token) while mechanical tasks continue on local LLM. If the API key is absent or Claude API quota is also exhausted, all tasks fall back to local LLM. Restores to normal when quota recovers.
- **Context Courier:** Before sending any task to the local LLM, pedalpoint greps your codebase for existing patterns and passes those files to the server. Local LLMs only get tasks they have templates for.
- **Drafts, not re-typing:** The server writes the local model's output straight to `<file>.draft` (only inside the current git repo). Claude reads it, fixes what's wrong, and promotes it with `mv` — it never re-types the code, which is where the token savings come from.
- **Proof:** `pedalpoint stats` reports net Claude output tokens saved per model per week, using real token counts from Claude Code transcripts.
- **Single install:** One script installs the MCP server, pulls the default model, and registers the companion skill.

## Requirements

- Claude Code
- Python 3.11+
- Apple Silicon: [mlx-lm](https://github.com/ml-explore/mlx-lm) (installed by the script), or
- Elsewhere: [Ollama](https://ollama.ai) (or any OpenAI-compatible inference server)

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | sh
```

The backend defaults to `mlx` on Apple Silicon and `ollama` elsewhere. To choose explicitly, or use a custom model or endpoint:

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | \
  sh -s -- --backend ollama --model llama3 --base-url http://localhost:11434/v1
```

Existing installs keep working as Ollama. Re-run with `--backend mlx` to switch.

Restart Claude Code after install.

> **Note:** If installing without the script, use `uv tool install pedalpoint` — not `pip install -e .`. The tool install puts `pedalpoint-server` in PATH where Claude Code can find it.

## Usage

**MLX starts itself.** The first `local_llm` call starts `mlx_lm.server` (that call takes ~10s longer while the model loads) and it stops after 20 minutes with no calls from any Claude Code session, freeing its ~5GB. A server you start by hand is used as-is and never stopped. Set `PEDALPOINT_AUTOSTART=0` to always manage it yourself:

```sh
mlx_lm.server --model mlx-community/gemma-4-e4b-it-4bit   # backend mlx, manual
ollama serve                                              # backend ollama (or open Ollama.app)
```

Ollama already unloads idle models on its own (`OLLAMA_KEEP_ALIVE`, default 5 minutes).

Then in any Claude Code session:

```
/route-tasks
```

pedalpoint handles routing automatically. No manual flagging needed.

To verify the MCP server connected:

```sh
claude mcp get pedalpoint
```

Should show `Status: ✓ Connected`. If disconnected, run `pedalpoint-server` directly to see the error.

## Modes

| Mode | Set via | Behavior |
|---|---|---|
| `hybrid` | default | Claude classifies each task into mechanical or structural (local draft, Claude reviews inline) or judgment (Agent only). Changes under ~30 lines skip the handoff. |
| `local-only` | `PEDALPOINT_MODE=local-only` | All tasks → local LLM (use when quota exhausted preemptively) |
| `passthrough` | `PEDALPOINT_MODE=passthrough` | All tasks → Claude Agent (disables pedalpoint) |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PEDALPOINT_BACKEND` | saved choice, else `mlx` on Apple Silicon / `ollama` elsewhere | `mlx` or `ollama`. If unset but `PEDALPOINT_BASE_URL` is set, inferred from the URL (port 11434 → `ollama`). Otherwise read from `~/.pedalpoint/backend`, which `install.sh` writes; re-running the installer keeps it unless you pass `--backend`. |
| `PEDALPOINT_BASE_URL` | mlx: `http://localhost:8080/v1`; ollama: `http://localhost:11434/v1` | OpenAI-compatible endpoint |
| `PEDALPOINT_MODEL` | mlx: `mlx-community/gemma-4-e4b-it-4bit`; ollama: `gemma4:12b` | Local model. See [Choosing a model](#choosing-a-model). |
| `PEDALPOINT_MODE` | `hybrid` | Routing mode |
| `PEDALPOINT_TIMEOUT` | `120` | Read timeout in seconds |
| `PEDALPOINT_AUTOSTART` | `1` | MLX only: start `mlx_lm.server` on the first call when it isn't running. `0` to manage it yourself. |
| `PEDALPOINT_IDLE_MINUTES` | `20` | MLX only: stop an auto-started server after this many minutes without calls from any session. |
| `PEDALPOINT_MAX_TOKENS` | `8192` | Max tokens per draft. Sent on every request (`mlx_lm.server` defaults to 512). Truncated output is rejected, never written. |
| `PEDALPOINT_INITIAL_FALLBACK_MINUTES` | `60` | Initial circuit-open duration (doubles on each probe failure) |
| `PEDALPOINT_API_MODEL` | `claude-sonnet-4-6` | Claude model used for API fallback |
| `ANTHROPIC_API_KEY` | (unset) | Anthropic API key for Claude API fallback tier. Optional — if unset, circuit skips `api_fallback` and goes directly to `open`. |

## Choosing a model

Measured on a 16GB M4 MacBook Air with normal apps open (four pedalpoint-style coding tasks, two runs):

| Model | Backend | Passed | Speed | Memory | Notes |
|---|---|---|---|---|---|
| `mlx-community/gemma-4-e4b-it-4bit` (default) | MLX | 4/4 · 4/4 | 25–28 tok/s | ~4–4.5GB | Most reliable |
| `mlx-community/Qwen3.5-4B-MLX-4bit` | MLX | 3/4 · 3/4 | 29 tok/s | ~3GB | Lighter; consistently fumbles test-writing |
| `gemma4:12b` | Ollama | 4/4 | 9.5 tok/s | ~7.5GB | Accurate but slow; pushes a 16GB Mac into swap |

Download a different MLX model with `uvx --from huggingface_hub hf download <repo>`, set `PEDALPOINT_MODEL`, and restart Claude Code (an auto-started server picks up the new model the next time it starts). `pedalpoint stats` shows whether a model pays off on your real work.

## Measuring savings

```sh
pedalpoint stats            # last 7 days
pedalpoint stats --days 30
```

For each model and week: handoffs, average score (1–7, what Claude had to do with the draft), redo rate, local tokens, **net Claude output tokens saved**, input overhead, and the share of rows estimated rather than measured. Rows flagged `NOT PAYING OFF` have an average score under 5 or a net saving ≤ 0. Handoffs are logged to `~/.pedalpoint/handoffs.jsonl`.

## Uninstall

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | sh -s -- --uninstall
```

## Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| `local_llm` calls fail with "MLX not reachable" | Autostart is off or the URL isn't local: `mlx_lm.server --model <model>` |
| "MLX server did not start" / "exited while starting" | Read `~/.pedalpoint/mlx.log` |
| "mlx_lm.server not found" | `uv tool install mlx-lm` |
| `local_llm` calls fail with "Ollama not reachable" | `ollama serve` (or open Ollama.app on macOS) |
| `local_llm` fails with "Model … not found" | The error includes the download command (`hf download …` or `ollama pull …`) |
| `local_llm` fails with "outside the project repo" or "Not in a git repository" | Start Claude Code from inside the project's git repo |
| Drafts land in the main checkout instead of your worktree | Update the skill (re-run install.sh): it passes `worktree` so drafts go to the session's current worktree |
| Anything else | `pedalpoint doctor` |
| `/route-tasks` says `local_llm` tool not available | `claude mcp get pedalpoint` (check status; if missing, re-run install) |
| `claude_api` returns "ANTHROPIC_API_KEY not set" — api_fallback tier disabled | `export ANTHROPIC_API_KEY=sk-ant-...` then restart Claude Code |
| All tasks route to local LLM even after Claude quota resets | `echo '{"circuit":"closed"}' > ~/.pedalpoint/state.json` |

## Development

```sh
git clone https://github.com/EMSwank/pedalpoint
cd pedalpoint
uv sync --extra dev   # or: pip install -e ".[dev]"
pytest tests/unit/ -v
```

Integration tests (require a running model server):

```sh
PEDALPOINT_INTEGRATION=true PEDALPOINT_BACKEND=ollama pytest tests/integration/test_ollama.py -v
PEDALPOINT_INTEGRATION=true PEDALPOINT_BACKEND=mlx pytest tests/integration/test_mlx.py -v
```

Install script tests (requires [bats-core](https://github.com/bats-core/bats-core)):

```sh
brew install bats-core   # macOS; use apt-get install bats on Linux
bats tests/install/
```

## License

MIT
