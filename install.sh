#!/usr/bin/env sh
set -e

# Defaults
PEDALPOINT_MODEL="${PEDALPOINT_MODEL:-gemma4:e4b}"
PEDALPOINT_BASE_URL="${PEDALPOINT_BASE_URL:-http://localhost:11434/v1}"
UNINSTALL=0

# Parse arguments
while [ "$#" -gt 0 ]; do
  case "$1" in
    --model)      PEDALPOINT_MODEL="$2";    shift 2 ;;
    --base-url)   PEDALPOINT_BASE_URL="$2"; shift 2 ;;
    --uninstall)  UNINSTALL=1;              shift   ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 1 ;;
  esac
done

SKILL_DIR="${HOME}/.claude/skills/route-tasks"
STATE_DIR="${HOME}/.pedalpoint"
PEDALPOINT_RAW="https://raw.githubusercontent.com/EMSwank/pedalpoint/main"

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
  printf '\nRemove ~/.pedalpoint/ (fallback logs and state)? [y/N] '
  read -r answer
  case "$answer" in
    [Yy]*) rm -rf "$STATE_DIR"; printf '✓ Removed %s\n' "$STATE_DIR" ;;
    *)     printf '→ Kept %s\n' "$STATE_DIR" ;;
  esac

  printf '\n✓ pedalpoint uninstalled. Restart Claude Code.\n'
  exit 0
fi

# ── Install ──────────────────────────────────────────────────────────────────

printf '→ Checking prerequisites...\n'

# Python 3.11+ — try versioned binaries if python3 is too old
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
  printf 'ERROR: Python 3.11+ required (found: %s). Install Python 3.11+ or add it to PATH.\n' \
    "$_found" >&2
  exit 1
fi

# curl or git (needed for install itself)
if ! command -v curl >/dev/null 2>&1 && ! command -v git >/dev/null 2>&1; then
  printf 'ERROR: curl or git required.\n' >&2; exit 1
fi

# Ollama reachable (warn only)
OLLAMA_AVAILABLE=0
if curl -sf "${PEDALPOINT_BASE_URL}/models" >/dev/null 2>&1; then
  OLLAMA_AVAILABLE=1
else
  printf 'WARNING: Ollama not reachable at %s\n' "$PEDALPOINT_BASE_URL"
  printf '         Install Ollama or update PEDALPOINT_BASE_URL.\n'
fi

# ollama CLI (warn only)
OLLAMA_CLI=0
if command -v ollama >/dev/null 2>&1; then
  OLLAMA_CLI=1
else
  printf 'WARNING: ollama CLI not found — model pull will be skipped.\n'
fi

# ── Step 2: Detect package manager ──────────────────────────────────────────
if command -v uv >/dev/null 2>&1; then
  PKG_MGR="uv"
elif command -v pipx >/dev/null 2>&1; then
  PKG_MGR="pipx"
else
  PKG_MGR="pip"
fi

# ── Step 3: Install Python package ──────────────────────────────────────────
printf '→ Installing pedalpoint via %s...\n' "$PKG_MGR"
case "$PKG_MGR" in
  uv)   uv tool install pedalpoint ;;
  pipx) pipx install pedalpoint 2>/dev/null || pipx upgrade pedalpoint ;;
  pip)  pip install --user pedalpoint ;;
esac

# ── Step 3.5: Verify server binary is in PATH ────────────────────────────────
export PATH="$HOME/.local/bin:$PATH"
if ! command -v pedalpoint-server >/dev/null 2>&1; then
  printf 'ERROR: pedalpoint-server not found in PATH after install.\n' >&2
  printf '  Run: export PATH="$HOME/.local/bin:$PATH"\n' >&2
  printf '  Then restart your shell and re-run this script.\n' >&2
  exit 1
fi
printf '✓ pedalpoint-server in PATH: %s\n' "$(command -v pedalpoint-server)"

# ── Step 4: Pull default model ───────────────────────────────────────────────
if [ "$OLLAMA_AVAILABLE" = "1" ] && [ "$OLLAMA_CLI" = "1" ]; then
  printf '→ Pulling model %s...\n' "$PEDALPOINT_MODEL"
  if ! ollama pull "$PEDALPOINT_MODEL"; then
    printf 'ERROR: Could not pull %s.\n' "$PEDALPOINT_MODEL" >&2
    printf '  Run: ollama pull %s\n' "$PEDALPOINT_MODEL" >&2
    exit 1
  fi
else
  printf 'WARNING: Skipping model pull. Run manually: ollama pull %s\n' "$PEDALPOINT_MODEL"
fi

# ── Step 6: Install companion skill ─────────────────────────────────────────
printf '→ Installing companion skill...\n'
mkdir -p "${SKILL_DIR}"
curl -fsSL "${PEDALPOINT_RAW}/skills/route-tasks/SKILL.md" \
  -o "${SKILL_DIR}/SKILL.md"

# ── Step 7: Register MCP server ─────────────────────────────────────────────
printf '→ Registering MCP server via claude mcp add...\n'

if ! command -v claude >/dev/null 2>&1; then
  printf 'ERROR: claude CLI not found — install Claude Code first.\n' >&2
  exit 1
fi

claude mcp remove pedalpoint -s user 2>/dev/null || true
claude mcp add pedalpoint pedalpoint-server --scope user \
  -e "PEDALPOINT_BASE_URL=${PEDALPOINT_BASE_URL}" \
  -e "PEDALPOINT_MODEL=${PEDALPOINT_MODEL}" \
  -e "PEDALPOINT_MODE=hybrid" \
  -e "PEDALPOINT_TIMEOUT=120"

# ── Step 8: Create state directory ──────────────────────────────────────────
mkdir -p "$STATE_DIR"

# ── Step 9: Summary ──────────────────────────────────────────────────────────
printf '\n'
printf '✓ pedalpoint installed!\n'
printf '✓ MCP server:  pedalpoint-server (user scope)\n'
printf '✓ Skill:       /route-tasks\n'
printf '✓ State dir:   %s\n' "$STATE_DIR"
printf '\n'
printf '→ Restart Claude Code to activate.\n'
printf '→ Then invoke: /route-tasks\n'
