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
printf '%s\n' "$*" >> "$HOME/.curl_args"
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

  # Hermetic stubs: record arguments instead of touching real tools/config
  for _tool in claude ollama uvx pedalpoint-server; do
    stub_recorder "$_tool"
  done
  printf '#!/bin/sh\nprintf "pedalpoint 0.4.0\\n"\n' > "$STUB_DIR/pedalpoint"
  chmod +x "$STUB_DIR/pedalpoint"
  stub_platform Linux x86_64
}

# stub_recorder TOOL — stub that appends its arguments to $HOME/.TOOL_args
stub_recorder() {
  printf '#!/bin/sh\nprintf "%%s\\n" "$*" >> "$HOME/.%s_args"\nexit 0\n' "$1" \
    > "$STUB_DIR/$1"
  chmod +x "$STUB_DIR/$1"
}

# stub_platform SYSTEM MACHINE — fake `uname -s` / `uname -m`
stub_platform() {
  printf '#!/bin/sh\n[ "$1" = "-m" ] && { printf "%s\\n"; exit 0; }\nprintf "%s\\n"\n' \
    "$2" "$1" > "$STUB_DIR/uname"
  chmod +x "$STUB_DIR/uname"
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

# ── MCP registration ──────────────────────────────────────────────────────────

@test "registers MCP server via claude mcp add with backend env" {
  run sh "$INSTALL_SH" --backend ollama
  [ "$status" -eq 0 ]
  grep -q "mcp add pedalpoint pedalpoint-server --scope user" "$HOME/.claude_args"
  grep -q "PEDALPOINT_BACKEND=ollama" "$HOME/.claude_args"
  grep -q "PEDALPOINT_BASE_URL=http://localhost:11434/v1" "$HOME/.claude_args"
  grep -q "PEDALPOINT_MODEL=gemma4:12b" "$HOME/.claude_args"
}

# ── Backends ──────────────────────────────────────────────────────────────────

@test "--backend mlx installs mlx-lm, downloads model, skips ollama" {
  stub_recorder uv
  run sh "$INSTALL_SH" --backend mlx
  [ "$status" -eq 0 ]
  [ ! -f "$HOME/.ollama_args" ]
  grep -q "tool install mlx-lm" "$HOME/.uv_args"
  grep -q -- "--from huggingface_hub hf download mlx-community/gemma-4-e4b-it-4bit" \
    "$HOME/.uvx_args"
  grep -q "PEDALPOINT_BACKEND=mlx" "$HOME/.claude_args"
  grep -q "PEDALPOINT_BASE_URL=http://localhost:8080/v1" "$HOME/.claude_args"
  grep -q "PEDALPOINT_MODEL=mlx-community/gemma-4-e4b-it-4bit" "$HOME/.claude_args"
  printf '%s\n' "$output" | grep -q "MLX starts automatically on first use"
}

@test "mlx model download failure warns but does not abort" {
  printf '#!/bin/sh\nexit 1\n' > "$STUB_DIR/uvx"
  chmod +x "$STUB_DIR/uvx"
  run sh "$INSTALL_SH" --backend mlx
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" | grep -q "WARNING: Could not download"
}

@test "--backend ollama pulls the model" {
  # reachability check must succeed for the pull path: any curl without -o passes
  cat > "$STUB_DIR/curl" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$HOME/.curl_args"
out=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    *)  shift ;;
  esac
done
[ -z "$out" ] && exit 0
mkdir -p "$(dirname "$out")"
printf '# stub skill\n' > "$out"
EOF
  chmod +x "$STUB_DIR/curl"
  run sh "$INSTALL_SH" --backend ollama
  [ "$status" -eq 0 ]
  grep -q "pull gemma4:12b" "$HOME/.ollama_args"
}

@test "default backend is mlx on Apple Silicon" {
  stub_platform Darwin arm64
  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  grep -q "PEDALPOINT_BACKEND=mlx" "$HOME/.claude_args"
}

@test "default backend is ollama elsewhere" {
  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  grep -q "PEDALPOINT_BACKEND=ollama" "$HOME/.claude_args"
}

@test "re-run keeps backend saved in ~/.pedalpoint/backend" {
  stub_platform Darwin arm64
  mkdir -p "$HOME/.pedalpoint"
  printf 'ollama\n' > "$HOME/.pedalpoint/backend"
  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  grep -q "PEDALPOINT_BACKEND=ollama" "$HOME/.claude_args"
}

@test "re-run of a 0.3 Ollama install keeps ollama" {
  stub_platform Darwin arm64
  cat > "$STUB_DIR/claude" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$HOME/.claude_args"
if [ "$1 $2" = "mcp get" ]; then
  printf '  Environment:\n    PEDALPOINT_BASE_URL=http://localhost:11434/v1\n'
fi
exit 0
EOF
  chmod +x "$STUB_DIR/claude"
  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  grep -q "PEDALPOINT_BACKEND=ollama" "$HOME/.claude_args"
}

@test "--backend overrides saved backend and is saved" {
  mkdir -p "$HOME/.pedalpoint"
  printf 'ollama\n' > "$HOME/.pedalpoint/backend"
  run sh "$INSTALL_SH" --backend mlx
  [ "$status" -eq 0 ]
  grep -q "PEDALPOINT_BACKEND=mlx" "$HOME/.claude_args"
  [ "$(cat "$HOME/.pedalpoint/backend")" = "mlx" ]
}

@test "--model overrides backend default" {
  run sh "$INSTALL_SH" --backend mlx --model mlx-community/Qwen3.5-4B-MLX-4bit
  [ "$status" -eq 0 ]
  grep -q "PEDALPOINT_MODEL=mlx-community/Qwen3.5-4B-MLX-4bit" "$HOME/.claude_args"
}

@test "unknown backend exits 1" {
  run sh "$INSTALL_SH" --backend foo
  [ "$status" -eq 1 ]
  printf '%s\n' "$output" | grep -q "Unknown backend"
}

# ── Skill version pinning ─────────────────────────────────────────────────────

@test "skill fetched from release tag matching installed version" {
  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  grep -q "/v0.4.0/skills/route-tasks/SKILL.md" "$HOME/.curl_args"
}

@test "skill falls back to main with warning when version unknown" {
  printf '#!/bin/sh\nexit 1\n' > "$STUB_DIR/pedalpoint"
  chmod +x "$STUB_DIR/pedalpoint"
  run sh "$INSTALL_SH"
  [ "$status" -eq 0 ]
  grep -q "/main/skills/route-tasks/SKILL.md" "$HOME/.curl_args"
  printf '%s\n' "$output" | grep -q "WARNING: could not determine pedalpoint version"
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

@test "uv install upgrades an existing pedalpoint" {
  stub_recorder uv
  run sh "$INSTALL_SH" --backend ollama
  [ "$status" -eq 0 ]
  grep -q "tool install --upgrade pedalpoint" "$HOME/.uv_args"
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
