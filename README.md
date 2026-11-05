# pedalpoint

[![Latest version on PyPI](https://img.shields.io/pypi/v/pedalpoint?color=2e7d32)](https://pypi.org/project/pedalpoint/) [![Supported Python versions](https://img.shields.io/pypi/pyversions/pedalpoint?color=2e7d32)](https://pypi.org/project/pedalpoint/) [![Test status for the main branch](https://img.shields.io/github/actions/workflow/status/EMSwank/pedalpoint/ci.yml?branch=main&label=tests&color=2e7d32)](https://github.com/EMSwank/pedalpoint/actions/workflows/ci.yml) [![MIT license](https://img.shields.io/github/license/EMSwank/pedalpoint?color=2e7d32)](https://github.com/EMSwank/pedalpoint/blob/main/LICENSE)

**Make your Claude Code usage go further.** pedalpoint hands routine coding tasks to a language model running on your own computer. Claude reviews the result instead of writing it, and you get real numbers showing what that saved.

It has two parts: a [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that talks to your local model, and a Claude Code skill, `/route-tasks`, that decides which tasks to hand off.

## Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Install](#install)
- [Usage](#usage)
- [Routing modes](#routing-modes)
- [Configuration](#configuration)
- [Commands](#commands)
- [Choosing a model](#choosing-a-model)
- [Measuring savings](#measuring-savings)
- [Privacy and security](#privacy-and-security)
- [Troubleshooting](#troubleshooting)
- [Uninstall](#uninstall)
- [Contributing](#contributing)
- [License](#license)

## How it works

Think of the local model as a junior developer and Claude as the senior developer who reviews the work.

1. **Claude sorts each task** in your plan by what it needs.

   | Task type | Examples | Who does it |
   |---|---|---|
   | Mechanical | Code that follows a pattern already in your project, test stubs, type hints | Local model drafts, Claude reviews |
   | Structural | Framework patterns, or tasks fully spelled out in a spec | Local model drafts, Claude reviews |
   | Judgment | Architecture, debugging, security, unclear requirements | Claude |

   Changes under about 30 lines skip the handoff, because Claude can make them for less than a handoff costs.

2. **Claude finds examples.** It searches your codebase for matching patterns and passes those file paths to the server. If it finds nothing to go on, Claude does the task itself.
3. **The local model writes a draft.** The server saves it as `<file>.draft`, inside your git repository. It never changes the real file.
4. **Claude reviews the draft,** fixes what's wrong, and moves it into place with `mv`. Claude never re-types the code, which is where the savings come from.
5. **Claude scores the draft** from 1 to 7, so `pedalpoint stats` can show whether handoffs are paying off.

### When your Claude usage runs out

pedalpoint keeps working in stages. It rechecks Claude after 60 minutes, doubling the wait after each failed check, and returns to normal once your usage is available again.

| Stage | When it applies | What happens |
|---|---|---|
| Normal | Claude is available | Tasks are routed as described above |
| API fallback | Usage ran out and `ANTHROPIC_API_KEY` is set | Judgment tasks go to the Claude API, billed per token. Other tasks stay on the local model |
| Local only | Usage ran out with no API key, or the API is out of quota too | All tasks go to the local model with no review. Commits are marked `[unreviewed]`, so check them afterward |

## Requirements

- [Claude Code](https://code.claude.com/docs)
- Python 3.11 or newer
- macOS or Linux, and `curl`
- [uv](https://docs.astral.sh/uv/), recommended. The installer also works with pipx or pip, but it uses uv to download MLX models
- A local model server:
  - On Apple Silicon Macs: [MLX](https://github.com/ml-explore/mlx-lm), which the installer sets up. The default model needs about 4.5GB of memory and 5.2GB of disk space
  - Anywhere else: [Ollama](https://ollama.com), or another server with an OpenAI-compatible API

## Install

1. Run the installer:

   ```sh
   curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | sh
   ```

2. Restart Claude Code.
3. Check that everything works:

   ```sh
   pedalpoint doctor
   ```

   On MLX, a warning that MLX is not running is normal. It starts when it's needed.

To read the script before running it, download it first:

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh -o install.sh
sh install.sh
```

### Installer options

Add options after `sh -s --`, or after `sh install.sh` if you downloaded the script:

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | \
  sh -s -- --backend ollama --model llama3
```

| Option | What it sets | Default |
|---|---|---|
| `--backend` | `mlx` or `ollama` | Your saved choice, then `mlx` on Apple Silicon and `ollama` elsewhere |
| `--model` | The local model | See [Choosing a model](#choosing-a-model) |
| `--base-url` | The model server's address | `http://localhost:8080/v1` for MLX, `http://localhost:11434/v1` for Ollama |

To remove pedalpoint, see [Uninstall](#uninstall). Run the installer again at any time to upgrade. It keeps your backend, but if you changed the model or address, pass `--model` or `--base-url` again.

To install without the script, use `uv tool install pedalpoint` rather than `pip install -e .`, so that Claude Code can find `pedalpoint-server`. You'll also need to copy the skill and register the server yourself, so the script is easier.

## Usage

Open Claude Code inside a git repository and run this when you're ready to work through an implementation plan:

```text
/route-tasks
```

pedalpoint routes each task for you, with nothing to flag by hand. It also works from a git worktree: drafts land in the worktree you're using.

### The model server

**On MLX, there's nothing to start or stop.** The first handoff starts the model server, which adds about 10 seconds to that call. It stops itself after 20 minutes with no handoffs from any Claude Code session, which frees its memory. Several sessions can share it safely.

If you start `mlx_lm.server` yourself, pedalpoint uses that server and never stops it.

**On Ollama,** start Ollama yourself by opening the app or running `ollama serve`. Ollama unloads idle models on its own.

## Routing modes

To change the mode, set `PEDALPOINT_MODE` in the shell that starts Claude Code. For example: `export PEDALPOINT_MODE=local-only`.

| Mode | What it does |
|---|---|
| `hybrid` | Default. Routes each task as described in [How it works](#how-it-works) |
| `local-only` | Sends every task to the local model. Useful when you know your usage is about to run out |
| `passthrough` | Sends every task to Claude, which turns pedalpoint off |

## Configuration

Most people won't need to change anything.

| Variable | Default | What it does |
|---|---|---|
| `PEDALPOINT_BACKEND` | Set by the installer | `mlx` or `ollama` |
| `PEDALPOINT_BASE_URL` | Set by the installer | Address of the model server. Any OpenAI-compatible server works |
| `PEDALPOINT_MODEL` | Set by the installer | Local model name |
| `PEDALPOINT_TIMEOUT` | `120` | Seconds to wait for the model |
| `PEDALPOINT_AUTOSTART` | `1` | MLX only. Set to `0` to start the model server yourself |
| `PEDALPOINT_IDLE_MINUTES` | `20` | MLX only. Minutes without a handoff before an automatically started server stops |
| `PEDALPOINT_MAX_TOKENS` | `8192` | Longest draft allowed, in tokens. Longer output is rejected rather than saved cut short |
| `PEDALPOINT_CONTEXT_LIMIT` | `16000` | Largest prompt allowed, in estimated tokens. Larger tasks go to Claude |
| `PEDALPOINT_API_MODEL` | `claude-sonnet-4-6` | Claude model used for API fallback |
| `ANTHROPIC_API_KEY` | Not set | Turns on API fallback. Without it, pedalpoint goes straight to local only |

### Change a setting

For the backend, address and model, re-run the installer with the matching option.

For anything else, export the variable in the shell that starts Claude Code, then restart Claude Code:

```sh
export PEDALPOINT_IDLE_MINUTES=10
```

Apps started outside a shell, such as the VS Code app opened from the Dock, may not see those exports. In that case, or to change `PEDALPOINT_TIMEOUT`, save the setting in the server's registration:

```sh
claude mcp remove pedalpoint -s user
claude mcp add pedalpoint pedalpoint-server --scope user \
  -e PEDALPOINT_BACKEND=mlx \
  -e PEDALPOINT_BASE_URL=http://localhost:8080/v1 \
  -e PEDALPOINT_MODEL=mlx-community/gemma-4-e4b-it-4bit \
  -e PEDALPOINT_MODE=hybrid \
  -e PEDALPOINT_TIMEOUT=120 \
  -e PEDALPOINT_IDLE_MINUTES=10
```

Re-running the installer replaces this registration, so add your settings again afterward.

## Commands

| Command | What it does |
|---|---|
| `pedalpoint doctor` | Checks your setup and prints a fix for each problem |
| `pedalpoint stats` | Shows tokens saved over the last 7 days |
| `pedalpoint stats --days 30` | Shows tokens saved over a longer period |
| `pedalpoint --version` | Shows the installed version |
| `claude mcp get pedalpoint` | Shows whether Claude Code is connected to the server |

## Choosing a model

These results come from a 16GB M4 MacBook Air with normal apps open, running four pedalpoint-style coding tasks.

| Model | Backend | Tasks passed | Tokens per second | Memory | Notes |
|---|---|---|---|---|---|
| `mlx-community/gemma-4-e4b-it-4bit` (default) | MLX | 4 of 4, in both runs | 25 to 28 | About 4.5GB | Most reliable |
| `mlx-community/Qwen3.5-4B-MLX-4bit` | MLX | 3 of 4, in both runs | 29 | About 3GB | Lighter, but failed the test-writing task both times |
| `gemma4:12b` (Ollama default) | Ollama | 4 of 4, in one run | 9.5 | About 7.5GB | Accurate but slow, and pushes a 16GB Mac into swap |

To try another model, run the installer again with `--model` and restart Claude Code. The installer downloads the model for you:

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | \
  sh -s -- --model mlx-community/Qwen3.5-4B-MLX-4bit
```

`pedalpoint stats` shows how each model does on your real work.

## Measuring savings

```sh
pedalpoint stats
```

The report has one row per model per week. This example is for illustration:

```text
model                              week      handoffs  avg score  redo %  local tok  output saved  new input  cached input  est %
mlx-community/gemma-4-e4b-it-4bit  2026-W45  12        6.1        8%      9400       3100          4100       36900         0%
```

| Column | Meaning |
|---|---|
| `handoffs` | Number of tasks handed to the local model |
| `avg score` | Average score, from the scale below |
| `redo %` | Share of drafts scored 1 or 2, meaning Claude started over |
| `local tok` | Tokens written by the local model |
| `output saved` | Claude output tokens saved after the cost of each handoff and review |
| `new input` | Tokens Claude read for the first time during reviews |
| `cached input` | Tokens Claude read again from its cache during reviews, usually most of the conversation so far |
| `est %` | Share of handoffs estimated because no Claude Code transcript was found. Estimated handoffs aren't counted in the input columns, which show a dash if none were measured |

A row marked `NOT PAYING OFF` has an average score under 5, or saved no output tokens overall.

That verdict leaves input out on purpose. Each step of a handoff also makes Claude read the conversation again, and Anthropic doesn't publish how plan limits count new and cached input. pedalpoint shows the numbers side by side rather than guess, so a row with no warning can still cost more than it saves. To see the effect on your own plan, compare your usage over similar sessions with and without handoffs.

| Score | What Claude had to do |
|---|---|
| 7 | Accepted the draft as it was |
| 6 | Fixed 1 to 3 lines |
| 5 | Made several fixes in the same file |
| 4 | Rewrote part of it |
| 3 | Rewrote most of it |
| 2 | Started over, but the draft helped |
| 1 | Started over, and the draft didn't help |

## Privacy and security

- **Your code stays on your computer** when the local model handles a task. It only reaches Anthropic through Claude, as usual, or through the Claude API if you turn on API fallback.
- **The server can only write `.draft` files,** and only inside your project's git repository or one of its worktrees. Claude Code's normal permissions apply when a draft is moved into place.
- **Records stay local.** Handoffs are logged to `~/.pedalpoint/handoffs.jsonl`, which holds file paths and token counts, not your code.
- **Unreviewed work is labeled.** In the local-only stage, commits are marked `[unreviewed]`.

To report a vulnerability, see the [security policy](https://github.com/EMSwank/pedalpoint/blob/main/SECURITY.md).

## Troubleshooting

Start with `pedalpoint doctor`, which checks your setup and suggests fixes.

| Problem | Fix |
|---|---|
| `/route-tasks` says the `local_llm` tool isn't available | Run `claude mcp get pedalpoint`. If it's missing, run the installer again. If it's disconnected, run `pedalpoint-server` to see the error |
| The skill says the server is older than the skill | Run the installer again, then restart Claude Code |
| "MLX not reachable" | Autostart is off, or the address isn't on this computer. Start the server with `mlx_lm.server --model <model>` |
| "MLX server did not start" or "exited while starting" | Read `~/.pedalpoint/mlx.log` |
| "mlx_lm.server not found" | Run `uv tool install mlx-lm` |
| "Ollama not reachable" | Open the Ollama app, or run `ollama serve` |
| "Model not found" | The error includes the download command |
| "Model timed out" | Your computer may be short on memory, so close some apps. Claude does that task instead, so no work is lost |
| "Outside the project repo" or "Not in a git repository" | Start Claude Code from inside your project's git repository |
| Drafts land in the main checkout instead of your worktree | Run the installer again to update the skill, then restart Claude Code |
| Tasks stay on the local model after your Claude usage returns | Run `echo '{"circuit":"closed"}' > ~/.pedalpoint/state.json` |
| "ANTHROPIC_API_KEY not set" | Run `export ANTHROPIC_API_KEY=<your key>`, then restart Claude Code. The key is only needed for API fallback |

## Uninstall

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | \
  sh -s -- --uninstall
```

This removes the server, the skill and the package, and asks before deleting `~/.pedalpoint/`. A running model server stops by itself after its idle time.

Downloaded models and `mlx-lm` stay in place, because other tools may use them. To remove them too:

```sh
uvx --from huggingface_hub hf cache rm model/mlx-community/gemma-4-e4b-it-4bit
uv tool uninstall mlx-lm
```

## Contributing

Contributions are welcome. See the [contributing guide](https://github.com/EMSwank/pedalpoint/blob/main/CONTRIBUTING.md) for setup and testing, the [changelog](https://github.com/EMSwank/pedalpoint/blob/main/CHANGELOG.md) for release history, and the [design history](https://github.com/EMSwank/pedalpoint/blob/main/docs/README.md) for how pedalpoint came to work this way.

## License

pedalpoint is released under the [MIT License](https://github.com/EMSwank/pedalpoint/blob/main/LICENSE).
