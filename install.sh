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

SKILL_DIR="${HOME}/.claude/plugins/pedalpoint"
MCP_CONFIG="${HOME}/.claude/mcp.json"
STATE_DIR="${HOME}/.pedalpoint"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Uninstall ────────────────────────────────────────────────────────────────
if [ "$UNINSTALL" = "1" ]; then
  printf '→ Uninstalling pedalpoint...\n'

  # Remove MCP entry
  if [ -f "$MCP_CONFIG" ] && command -v jq >/dev/null 2>&1; then
    tmp=$(mktemp)
    jq 'del(.mcpServers.pedalpoint)' "$MCP_CONFIG" > "$tmp"
    mv "$tmp" "$MCP_CONFIG"
    printf '✓ Removed pedalpoint from %s\n' "$MCP_CONFIG"
  fi

  # Remove skill
  rm -rf "$SKILL_DIR"
  printf '✓ Removed skill directory %s\n' "$SKILL_DIR"

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

# Python 3.11+
if ! command -v python3 >/dev/null 2>&1; then
  printf 'ERROR: python3 not found. Install Python 3.11+.\n' >&2; exit 1
fi
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null; then
  printf 'ERROR: Python 3.11+ required.\n' >&2; exit 1
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
  pipx) pipx install pedalpoint ;;
  pip)  pip install --user pedalpoint ;;
esac

# ── Step 4: Pull default model ───────────────────────────────────────────────
if [ "$OLLAMA_AVAILABLE" = "1" ] && [ "$OLLAMA_CLI" = "1" ]; then
  printf '→ Pulling model %s...\n' "$PEDALPOINT_MODEL"
  if ! ollama pull "$PEDALPOINT_MODEL"; then
    printf 'WARNING: Could not pull %s. Run manually: ollama pull %s\n' \
      "$PEDALPOINT_MODEL" "$PEDALPOINT_MODEL"
  fi
else
  printf 'WARNING: Skipping model pull. Run manually: ollama pull %s\n' "$PEDALPOINT_MODEL"
fi

# ── Step 6: Install companion skill ─────────────────────────────────────────
printf '→ Installing companion skill...\n'
mkdir -p "${SKILL_DIR}/skills"
cp "${SCRIPT_DIR}/skills/route-tasks.md" "${SKILL_DIR}/skills/"

# ── Step 7: Register MCP server ─────────────────────────────────────────────
printf '→ Registering MCP server in %s...\n' "$MCP_CONFIG"
ENTRY="{\"command\":\"pedalpoint-server\",\"args\":[],\"env\":{\"PEDALPOINT_BASE_URL\":\"${PEDALPOINT_BASE_URL}\",\"PEDALPOINT_MODEL\":\"${PEDALPOINT_MODEL}\",\"PEDALPOINT_MODE\":\"hybrid\",\"PEDALPOINT_TIMEOUT\":\"120\"}}"

if [ -f "$MCP_CONFIG" ] && command -v jq >/dev/null 2>&1; then
  tmp=$(mktemp)
  jq --argjson entry "$ENTRY" '.mcpServers.pedalpoint = $entry' "$MCP_CONFIG" > "$tmp"
  mv "$tmp" "$MCP_CONFIG"
elif [ ! -f "$MCP_CONFIG" ]; then
  mkdir -p "$(dirname "$MCP_CONFIG")"
  printf '{"mcpServers":{"pedalpoint":%s}}\n' "$ENTRY" > "$MCP_CONFIG"
else
  printf 'WARNING: jq not found — manually add pedalpoint to %s\n' "$MCP_CONFIG"
  printf 'Entry: {"mcpServers":{"pedalpoint":%s}}\n' "$ENTRY"
fi

# ── Step 8: Create state directory ──────────────────────────────────────────
mkdir -p "$STATE_DIR"

# ── Step 9: Summary ──────────────────────────────────────────────────────────
printf '\n'
printf '✓ pedalpoint installed!\n'
printf '✓ MCP server:  pedalpoint-server\n'
printf '✓ Skill:       pedalpoint:route-tasks\n'
printf '✓ Config:      %s\n' "$MCP_CONFIG"
printf '✓ State dir:   %s\n' "$STATE_DIR"
printf '\n'
printf '→ Restart Claude Code to activate.\n'
printf '→ Then invoke: pedalpoint:route-tasks\n'
