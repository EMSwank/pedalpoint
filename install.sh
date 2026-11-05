#!/usr/bin/env sh
set -e

# Defaults (model/base URL depend on the backend; resolved after parsing)
PEDALPOINT_BACKEND="${PEDALPOINT_BACKEND:-}"
PEDALPOINT_MODEL="${PEDALPOINT_MODEL:-}"
PEDALPOINT_BASE_URL="${PEDALPOINT_BASE_URL:-}"
UNINSTALL=0

# Parse arguments
while [ "$#" -gt 0 ]; do
  case "$1" in
    --backend)    PEDALPOINT_BACKEND="$2";  shift 2 ;;
    --model)      PEDALPOINT_MODEL="$2";    shift 2 ;;
    --base-url)   PEDALPOINT_BASE_URL="$2"; shift 2 ;;
    --uninstall)  UNINSTALL=1;              shift   ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 1 ;;
  esac
done

STATE_DIR="${HOME}/.pedalpoint"

# Backend: --backend > saved choice > existing registration > platform default
if [ -z "$PEDALPOINT_BACKEND" ] && [ -f "${STATE_DIR}/backend" ]; then
  PEDALPOINT_BACKEND=$(cat "${STATE_DIR}/backend")
fi
if [ -z "$PEDALPOINT_BACKEND" ] && command -v claude >/dev/null 2>&1; then
  _registered=$(claude mcp get pedalpoint 2>/dev/null || true)
  case "$_registered" in
    *PEDALPOINT_BACKEND=mlx*)    PEDALPOINT_BACKEND="mlx" ;;
    *PEDALPOINT_BACKEND=ollama*) PEDALPOINT_BACKEND="ollama" ;;
    *:11434*)                    PEDALPOINT_BACKEND="ollama" ;;  # pre-0.4 install
  esac
fi
if [ -z "$PEDALPOINT_BACKEND" ]; then
  if [ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ]; then
    PEDALPOINT_BACKEND="mlx"
  else
    PEDALPOINT_BACKEND="ollama"
  fi
fi
case "$PEDALPOINT_BACKEND" in
  mlx)
    PEDALPOINT_MODEL="${PEDALPOINT_MODEL:-mlx-community/gemma-4-e4b-it-4bit}"
    PEDALPOINT_BASE_URL="${PEDALPOINT_BASE_URL:-http://localhost:8080/v1}"
    ;;
  ollama)
    PEDALPOINT_MODEL="${PEDALPOINT_MODEL:-gemma4:12b}"
    PEDALPOINT_BASE_URL="${PEDALPOINT_BASE_URL:-http://localhost:11434/v1}"
    ;;
  *)
    printf 'Unknown backend: %s (use mlx or ollama)\n' "$PEDALPOINT_BACKEND" >&2
    exit 1
    ;;
esac

SKILL_DIR="${HOME}/.claude/skills/route-tasks"
PEDALPOINT_REPO_RAW="https://raw.githubusercontent.com/EMSwank/pedalpoint"

# ── Uninstall ────────────────────────────────────────────────────────────────
if [ "$UNINSTALL" = "1" ]; then
  printf '→ Uninstalling pedalpoint...\n'

  # Remove MCP entry
  if command -v claude >/dev/null 2>&1; then
    claude mcp remove pedalpoint -s user 2>/dev/null && \
      printf '✓ Removed pedalpoint MCP server\n' || true
  fi

  # Remove skill
  rm -rf "$SKILL_DIR"
  printf '✓ Removed skill %s\n' "$SKILL_DIR"

  # Uninstall package
  if command -v uv >/dev/null 2>&1; then
    uv tool uninstall pedalpoint 2>/dev/null || true
  elif command -v pipx >/dev/null 2>&1; then
    pipx uninstall pedalpoint 2>/dev/null || true
  else
    pip uninstall -y pedalpoint 2>/dev/null || true
  fi
  printf '✓ Package uninstalled\n'

  # Prompt before removing state
  printf '\nRemove ~/.pedalpoint/ (state, logs and savings history)? [y/N] '
  # Under `curl | sh`, stdin is this script, so the answer must come from the tty.
  answer=""
  { read -r answer <"${PEDALPOINT_TTY:-/dev/tty}"; } 2>/dev/null || true
  case "$answer" in
    [Yy]*) rm -rf "$STATE_DIR"; printf '✓ Removed %s\n' "$STATE_DIR" ;;
    *)     printf '→ Kept %s\n' "$STATE_DIR" ;;
  esac

  printf '\n✓ pedalpoint uninstalled. Restart Claude Code.\n'
  exit 0
fi

# ── Install ──────────────────────────────────────────────────────────────────

printf '→ Checking prerequisites...\n'

# Claude Code — check before installing or downloading anything
if ! command -v claude >/dev/null 2>&1; then
  printf 'ERROR: claude CLI not found. Install Claude Code first: https://code.claude.com/docs\n' >&2
  exit 1
fi

# Package manager
if command -v uv >/dev/null 2>&1; then
  PKG_MGR="uv"
elif command -v pipx >/dev/null 2>&1; then
  PKG_MGR="pipx"
else
  PKG_MGR="pip"
fi

# Python 3.11+ — uv fetches its own; otherwise try versioned binaries too
if [ "$PKG_MGR" != "uv" ]; then
  PYTHON3=""
  for _py in python3 python3.13 python3.12 python3.11; do
    if command -v "$_py" >/dev/null 2>&1 && \
       "$_py" -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
      PYTHON3="$_py"
      break
    fi
  done
  if [ -z "$PYTHON3" ]; then
    _found=$(python3 --version 2>&1 || printf 'not found')
    printf 'ERROR: Python 3.11+ required (found: %s).\n' "$_found" >&2
    printf '  Install uv, which fetches Python for you: https://docs.astral.sh/uv/\n' >&2
    exit 1
  fi
fi

# curl or git (needed for install itself)
if ! command -v curl >/dev/null 2>&1 && ! command -v git >/dev/null 2>&1; then
  printf 'ERROR: curl or git required.\n' >&2; exit 1
fi

OLLAMA_AVAILABLE=0
OLLAMA_CLI=0
if [ "$PEDALPOINT_BACKEND" = "ollama" ]; then
  # Ollama reachable (warn only)
  if curl -sf "${PEDALPOINT_BASE_URL}/models" >/dev/null 2>&1; then
    OLLAMA_AVAILABLE=1
  else
    printf 'WARNING: Ollama not reachable at %s\n' "$PEDALPOINT_BASE_URL"
    printf '         Install Ollama or update PEDALPOINT_BASE_URL.\n'
  fi

  # ollama CLI (warn only)
  if command -v ollama >/dev/null 2>&1; then
    OLLAMA_CLI=1
  else
    printf 'WARNING: ollama CLI not found — model pull will be skipped.\n'
  fi
fi

# ── Step 3: Install Python package ──────────────────────────────────────────
printf '→ Installing pedalpoint via %s...\n' "$PKG_MGR"
case "$PKG_MGR" in
  uv)   uv tool install --upgrade --refresh-package pedalpoint pedalpoint ;;
  pipx) pipx install pedalpoint 2>/dev/null || pipx upgrade pedalpoint ;;
  pip)  pip install --user --upgrade pedalpoint ;;
esac

# ── Step 3.5: Find the installed server ─────────────────────────────────────
# Only this script sees the PATH change below, so remember the user's own.
USER_PATH="$PATH"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v pedalpoint-server >/dev/null 2>&1; then
  printf 'ERROR: pedalpoint-server not found in PATH after install.\n' >&2
  printf '  Run: export PATH="$HOME/.local/bin:$PATH"\n' >&2
  printf '  Then restart your shell and re-run this script.\n' >&2
  exit 1
fi
SERVER_PATH=$(command -v pedalpoint-server)
USER_SERVER=$(PATH="$USER_PATH"; command -v pedalpoint-server 2>/dev/null) || true
printf '✓ pedalpoint-server installed: %s\n' "$SERVER_PATH"

# ── Step 4: Get the model ────────────────────────────────────────────────────
if [ "$PEDALPOINT_BACKEND" = "mlx" ]; then
  printf '→ Installing mlx-lm...\n'
  if command -v uv >/dev/null 2>&1; then
    uv tool install mlx-lm || printf 'WARNING: uv tool install mlx-lm failed.\n'
  elif command -v pipx >/dev/null 2>&1; then
    pipx install mlx-lm 2>/dev/null || pipx upgrade mlx-lm || \
      printf 'WARNING: pipx install mlx-lm failed.\n'
  else
    printf 'WARNING: uv/pipx not found — install mlx-lm manually: pip install mlx-lm\n'
  fi

  printf '→ Downloading model %s...\n' "$PEDALPOINT_MODEL"
  if ! uvx --from huggingface_hub hf download "$PEDALPOINT_MODEL"; then
    printf 'WARNING: Could not download %s.\n' "$PEDALPOINT_MODEL"
    printf '  Run: uvx --from huggingface_hub hf download %s\n' "$PEDALPOINT_MODEL"
  fi
elif [ "$OLLAMA_AVAILABLE" = "1" ] && [ "$OLLAMA_CLI" = "1" ]; then
  printf '→ Pulling model %s...\n' "$PEDALPOINT_MODEL"
  if ! ollama pull "$PEDALPOINT_MODEL"; then
    printf 'ERROR: Could not pull %s.\n' "$PEDALPOINT_MODEL" >&2
    printf '  Run: ollama pull %s\n' "$PEDALPOINT_MODEL" >&2
    exit 1
  fi
else
  printf 'WARNING: Skipping model pull. Run manually: ollama pull %s\n' "$PEDALPOINT_MODEL"
fi

# ── Step 6: Install companion skill (pinned to the installed release) ───────
printf '→ Installing companion skill...\n'
PEDALPOINT_VERSION=$(pedalpoint --version 2>/dev/null | awk '{print $2}') || true
if [ -n "$PEDALPOINT_VERSION" ]; then
  SKILL_REF="v${PEDALPOINT_VERSION}"
else
  SKILL_REF="main"
  printf 'WARNING: could not determine pedalpoint version — using skill from main.\n'
fi
mkdir -p "${SKILL_DIR}"
fetch_skill() {
  curl -fsSL "${PEDALPOINT_REPO_RAW}/$1/skills/route-tasks/SKILL.md" \
    -o "${SKILL_DIR}/SKILL.md"
}
if ! fetch_skill "$SKILL_REF"; then
  if [ "$SKILL_REF" = "main" ] || ! {
    printf 'WARNING: no skill for %s — using skill from main.\n' "$SKILL_REF"
    fetch_skill main
  }; then
    printf 'ERROR: could not download the skill from %s.\n' "$PEDALPOINT_REPO_RAW" >&2
    exit 1
  fi
fi

# ── Step 7: Register MCP server ─────────────────────────────────────────────
printf '→ Registering MCP server via claude mcp add...\n'

claude mcp remove pedalpoint -s user 2>/dev/null || true
# Full path: Claude Code's PATH may not include the install folder, or may find
# an older copy first.
claude mcp add pedalpoint "$SERVER_PATH" --scope user \
  -e "PEDALPOINT_BACKEND=${PEDALPOINT_BACKEND}" \
  -e "PEDALPOINT_BASE_URL=${PEDALPOINT_BASE_URL}" \
  -e "PEDALPOINT_MODEL=${PEDALPOINT_MODEL}" \
  -e "PEDALPOINT_MODE=hybrid" \
  -e "PEDALPOINT_TIMEOUT=120"

# ── Step 8: Create state directory, remember backend ────────────────────────
mkdir -p "$STATE_DIR"
printf '%s\n' "$PEDALPOINT_BACKEND" > "${STATE_DIR}/backend"

# ── Step 9: Summary ──────────────────────────────────────────────────────────
printf '\n'
printf '✓ pedalpoint installed!\n'
printf '✓ MCP server:  %s (user scope)\n' "$SERVER_PATH"
printf '✓ Skill:       /route-tasks\n'
printf '✓ State dir:   %s\n' "$STATE_DIR"
printf '✓ Backend:     %s (%s)\n' "$PEDALPOINT_BACKEND" "$PEDALPOINT_MODEL"
printf '\n'
if [ "$PEDALPOINT_BACKEND" = "mlx" ]; then
  printf '→ MLX starts automatically on first use and stops after 20 idle minutes\n'
  printf '  (set PEDALPOINT_IDLE_MINUTES, or PEDALPOINT_AUTOSTART=0 to manage it yourself).\n'
fi
if [ -z "$USER_SERVER" ]; then
  case "$PKG_MGR" in
    uv)   PATH_FIX='uv tool update-shell' ;;
    pipx) PATH_FIX='pipx ensurepath' ;;
    pip)  PATH_FIX="add $(dirname "$SERVER_PATH") to PATH in your shell profile" ;;
  esac
  printf 'WARNING: %s is not on your PATH, so the pedalpoint command won'"'"'t work\n' \
    "$(dirname "$SERVER_PATH")"
  printf '  in a new terminal. Claude Code can still start the server.\n'
  printf '  To fix it: %s\n' "$PATH_FIX"
elif [ "$USER_SERVER" != "$SERVER_PATH" ]; then
  printf 'WARNING: another pedalpoint-server comes first on your PATH: %s\n' "$USER_SERVER"
  printf '  Claude Code uses the new one, but the pedalpoint command may run the old\n'
  printf '  copy. Remove it, or put %s earlier on your PATH.\n' "$(dirname "$SERVER_PATH")"
fi
printf '→ Restart Claude Code to activate.\n'
printf '→ Then invoke: /route-tasks\n'
