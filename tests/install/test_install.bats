#!/usr/bin/env bats
#
# Tests for install.sh
# Requires bats-core:  brew install bats-core  |  apt-get install bats

INSTALL_SH="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)/install.sh"

setup() {
  export HOME
  HOME=$(mktemp -d)

  export STUB_DIR
  STUB_DIR=$(mktemp -d)
  export PATH="$STUB_DIR:$PATH"

  # python3: always passes version check
  printf '#!/bin/sh\nexit 0\n' > "$STUB_DIR/python3"
  chmod +x "$STUB_DIR/python3"

  # curl: skill download (has -o flag) writes dummy file and succeeds;
  #       other calls (ollama reachability check) fail → warn-only path in script
  cat > "$STUB_DIR/curl" <<'EOF'
#!/bin/sh
out=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    *)  shift ;;
  esac
done
[ -z "$out" ] && exit 1
mkdir -p "$(dirname "$out")"
printf '# stub skill\n' > "$out"
exit 0
EOF
  chmod +x "$STUB_DIR/curl"

  # Package manager stubs: shadow any system tools so install.sh doesn't
  # try to install an unpublished package from PyPI during tests
  printf '#!/bin/sh\nexit 0\n' > "$STUB_DIR/uv"
  chmod +x "$STUB_DIR/uv"
  printf '#!/bin/sh\nexit 0\n' > "$STUB_DIR/pipx"
  chmod +x "$STUB_DIR/pipx"
  printf '#!/bin/sh\nexit 0\n' > "$STUB_DIR/pip"
  chmod +x "$STUB_DIR/pip"
}

teardown() {
  rm -rf "$HOME" "$STUB_DIR"
}

# ── Skill download (main bug fix) ─────────────────────────────────────────────

@test "skill file lands at correct path" {
  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  [ -f "$HOME/.claude/skills/route-tasks/SKILL.md" ]
}

@test "curl-pipe scenario: works from empty tmpdir with no skills/ subdir" {
  empty_dir=$(mktemp -d)
  cd "$empty_dir"
  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  [ -f "$HOME/.claude/skills/route-tasks/SKILL.md" ]
}

@test "skill download curl failure aborts install" {
  # curl -f returns 22 on HTTP error; set -e in install.sh aborts on non-zero
  printf '#!/bin/sh\nexit 22\n' > "$STUB_DIR/curl"
  chmod +x "$STUB_DIR/curl"

  run sh "$INSTALL_SH"
  [ "$status" -ne 0 ]
}

# ── MCP config ────────────────────────────────────────────────────────────────

@test "mcp.json created from scratch when absent" {
  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  [ -f "$HOME/.claude/mcp.json" ]
  grep -q '"pedalpoint"' "$HOME/.claude/mcp.json"
}

@test "mcp.json present + jq present: entry written via jq" {
  cat > "$STUB_DIR/jq" <<'EOF'
#!/bin/sh
printf '{"mcpServers":{"pedalpoint":{"command":"pedalpoint-server"}}}\n'
exit 0
EOF
  chmod +x "$STUB_DIR/jq"

  mkdir -p "$HOME/.claude"
  printf '{"mcpServers":{}}\n' > "$HOME/.claude/mcp.json"

  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  grep -q '"pedalpoint"' "$HOME/.claude/mcp.json"
}

@test "mcp.json present + jq absent exits 1 with helpful message" {
  if command -v jq >/dev/null 2>&1; then
    skip "system jq present — cannot test jq-absent path portably"
  fi

  mkdir -p "$HOME/.claude"
  printf '{"mcpServers":{}}\n' > "$HOME/.claude/mcp.json"

  run sh "$INSTALL_SH"
  [ "$status" -eq 1 ]
  printf '%s\n' "${output}" | grep -q "jq not found"
}

# ── JSON injection guards ─────────────────────────────────────────────────────

@test "PEDALPOINT_MODEL with double-quote rejected" {
  run sh "$INSTALL_SH" --model 'bad"model'
  [ "$status" -eq 1 ]
}

@test "PEDALPOINT_BASE_URL with backslash rejected" {
  run sh "$INSTALL_SH" --base-url 'http://bad\host'
  [ "$status" -eq 1 ]
}

# ── Package manager detection ─────────────────────────────────────────────────

@test "uv used when present" {
  # STUB_DIR is prepended to PATH, so this stub shadows any system uv
  cat > "$STUB_DIR/uv" <<'EOF'
#!/bin/sh
printf 'uv\n' > "${HOME}/.pkg_called"
exit 0
EOF
  chmod +x "$STUB_DIR/uv"

  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  [ -f "$HOME/.pkg_called" ]
  grep -q "uv" "$HOME/.pkg_called"
}

@test "pipx used when uv absent" {
  # Remove uv stub so command -v uv falls through to system; skip if system uv present
  rm -f "$STUB_DIR/uv"
  if command -v uv >/dev/null 2>&1; then
    skip "system uv in PATH — cannot test pipx-fallback portably"
  fi

  cat > "$STUB_DIR/pipx" <<'EOF'
#!/bin/sh
printf 'pipx\n' > "${HOME}/.pkg_called"
exit 0
EOF
  chmod +x "$STUB_DIR/pipx"

  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  [ -f "$HOME/.pkg_called" ]
  grep -q "pipx" "$HOME/.pkg_called"
}

@test "pip used when uv and pipx absent" {
  # Remove uv+pipx stubs; skip if either is present in system PATH
  rm -f "$STUB_DIR/uv" "$STUB_DIR/pipx"
  if command -v uv >/dev/null 2>&1 || command -v pipx >/dev/null 2>&1; then
    skip "uv or pipx in PATH — cannot test pip-fallback portably"
  fi

  cat > "$STUB_DIR/pip" <<'EOF'
#!/bin/sh
printf 'pip\n' > "${HOME}/.pkg_called"
exit 0
EOF
  chmod +x "$STUB_DIR/pip"

  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  grep -q "pip" "$HOME/.pkg_called"
}

# ── Python version fallback ───────────────────────────────────────────────────

@test "python3.11 used when python3 is too old" {
  # python3 stub: fails version check (simulates 3.9)
  printf '#!/bin/sh\n[ "$1" = "--version" ] && { printf "Python 3.9.6\n"; exit 0; }; exit 1\n' \
    > "$STUB_DIR/python3"
  chmod +x "$STUB_DIR/python3"

  # python3.11 stub: passes version check
  printf '#!/bin/sh\nexit 0\n' > "$STUB_DIR/python3.11"
  chmod +x "$STUB_DIR/python3.11"

  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
}

@test "no python 3.11+ anywhere exits 1 with helpful message" {
  # python3 stub: fails version check and reports version via --version
  printf '#!/bin/sh\n[ "$1" = "--version" ] && { printf "Python 3.9.6\n"; exit 0; }; exit 1\n' \
    > "$STUB_DIR/python3"
  chmod +x "$STUB_DIR/python3"
  # shadow all versioned binaries so system python3.11/3.12/3.13 can't be found
  for _py in python3.11 python3.12 python3.13; do
    printf '#!/bin/sh\nexit 1\n' > "$STUB_DIR/$_py"
    chmod +x "$STUB_DIR/$_py"
  done

  run sh "$INSTALL_SH"
  [ "$status" -eq 1 ]
  printf '%s\n' "${output}" | grep -q "Python 3.11+ required"
}

# ── Uninstall ─────────────────────────────────────────────────────────────────

@test "uninstall removes skill dir" {
  mkdir -p "$HOME/.claude/skills/route-tasks"
  printf '# skill\n' > "$HOME/.claude/skills/route-tasks/SKILL.md"

  answer=$(mktemp)
  printf 'n\n' > "$answer"
  run sh "$INSTALL_SH" --uninstall < "$answer"
  rm -f "$answer"

  [ "$status" -eq 0 ]
  [ ! -d "$HOME/.claude/skills/route-tasks" ]
}
