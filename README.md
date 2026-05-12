# pedalpoint

Route mechanical development tasks to a local LLM (Ollama, LM Studio, Jan) via Claude Code. Automatically falls back to local-only mode when Claude quota is exhausted.

## What it does

- **Hybrid routing:** Claude classifies each task. Mechanical work (scaffolding, CRUD, test stubs) goes to your local LLM. Judgment work (architecture, debugging, integration) stays with Claude.
- **Three-tier quota fallback:** When Claude Pro returns a quota error, pedalpoint first routes judgment and structural tasks to Claude API (pay-per-token) while mechanical tasks continue on local LLM. If the API key is absent or Claude API quota is also exhausted, all tasks fall back to local LLM. Restores to normal when quota recovers.
- **Context Courier:** Before sending any task to the local LLM, pedalpoint greps your codebase for existing patterns and injects them into the prompt. Local LLMs only get tasks they have templates for.
- **Single install:** One script installs the MCP server, pulls the default model, and registers the companion skill.

## Requirements

- Claude Code
- Python 3.11+
- [Ollama](https://ollama.ai) (or any OpenAI-compatible inference server)

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | sh
```

With a custom model or endpoint:

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | \
  sh -s -- --model llama3 --base-url http://localhost:11434/v1
```

Restart Claude Code after install.

## Usage

Ollama must be running before you open Claude Code:

```sh
ollama serve          # or open Ollama.app on macOS
```

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
| `hybrid` | default | Claude classifies each task into mechanical (local LLM direct), structural (local LLM draft + Agent review), or judgment (Agent only) |
| `local-only` | `PEDALPOINT_MODE=local-only` | All tasks → local LLM (use when quota exhausted preemptively) |
| `passthrough` | `PEDALPOINT_MODE=passthrough` | All tasks → Claude Agent (disables pedalpoint) |

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PEDALPOINT_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint |
| `PEDALPOINT_MODEL` | `gemma4:e4b` | Default local model |
| `PEDALPOINT_MODE` | `hybrid` | Routing mode |
| `PEDALPOINT_TIMEOUT` | `120` | Read timeout in seconds |
| `PEDALPOINT_INITIAL_FALLBACK_MINUTES` | `60` | Initial circuit-open duration (doubles on each probe failure) |
| `PEDALPOINT_API_MODEL` | `claude-sonnet-4-6` | Claude model used for API fallback |
| `ANTHROPIC_API_KEY` | (unset) | Anthropic API key for Claude API fallback tier. Optional — if unset, circuit skips `api_fallback` and goes directly to `open`. |

## Uninstall

```sh
curl -fsSL https://raw.githubusercontent.com/EMSwank/pedalpoint/main/install.sh | sh -s -- --uninstall
```

## Development

```sh
git clone https://github.com/EMSwank/pedalpoint
cd pedalpoint
uv sync --extra dev   # or: pip install -e ".[dev]"
pytest tests/unit/ -v
```

Integration tests (requires Ollama running):

```sh
PEDALPOINT_INTEGRATION=true pytest tests/integration/ -v
```

Install script tests (requires [bats-core](https://github.com/bats-core/bats-core)):

```sh
brew install bats-core   # macOS; use apt-get install bats on Linux
bats tests/install/
```

## License

MIT
