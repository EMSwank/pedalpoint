# Changelog

Notable changes to pedalpoint, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## Unreleased

### Changed

- `pedalpoint stats` shows new and cached input in separate columns, beside the
  output tokens saved. The `net saved` column is now `output saved`, and
  `input overhead` is replaced by `new input` and `cached input`.
- A note under the report says the verdict covers output tokens and scores only.

### Fixed

- Rows with no measured handoffs show a dash for input instead of a false 0.
- The installer registers the server by its full path, so Claude Code finds it
  even when the install folder isn't on PATH, and never starts an older copy.
- The installer warns if the install folder isn't on your PATH, or if another
  `pedalpoint-server` comes first. It used to report success in both cases.
- The installer checks for Claude Code before installing or downloading anything.
- With uv, the installer no longer stops on an old system Python, because uv
  fetches a suitable one. This includes a new Mac, which ships Python 3.9.

## 0.5.2 - 2026-11-05

### Fixed

- `pedalpoint stats` now finds handoffs in real Claude Code transcripts. Until
  now it never matched them, so every number it reported was an estimate.

## 0.5.1 - 2026-11-04

### Fixed

- Drafts of files containing code fences or `<think>` inside string literals are
  no longer cut short.
- A model reply with no content counts as empty output instead of crashing.
- A line range past the end of a file is a clear error instead of empty context.
- Files over 2MB are refused before they are read.
- A git repository at your home directory no longer becomes the project for
  every folder below it.
- `pedalpoint stats` now reads subagent transcripts, handles resumed sessions,
  and counts a request shared by two handoffs once.
- The installer checks PyPI for the newest pedalpoint instead of trusting a
  cached package list.
- When a release tag is missing, the installer uses the skill from `main` and
  warns you. If the download fails, it says why.
- `install.sh --uninstall` now waits for your answer when run through `curl | sh`.

### Changed

- Measuring change size is faster on heavily edited files.
- `pedalpoint stats` skips transcripts older than the reporting window.

### Added

- `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` and package
  metadata for PyPI.

## 0.5.0 - 2026-10-26

### Added

- The MLX model server starts on the first handoff and stops after 20 idle
  minutes. Settings: `PEDALPOINT_AUTOSTART` and `PEDALPOINT_IDLE_MINUTES`.
- `local_llm` and `claude_api` accept a `worktree` argument, so drafts land in
  the git worktree you are working in.

## 0.4.0 - 2026-10-26

### Added

- MLX backend for Apple Silicon, with Ollama kept as an option.
- `pedalpoint stats` and the `record_outcome` tool, which report net Claude
  tokens saved using real transcript data.

### Changed

- The server now writes model output to `<file>.draft`, and Claude promotes it
  with `mv` instead of re-typing the code.
- `local_llm` and `claude_api` take file paths instead of pasted code.

### Fixed

- `mcp`, `httpx` and `anthropic` are capped below their next major versions.
  `mcp` 2 broke fresh installs of earlier releases.

## 0.3.0 - 2026-05-12

### Fixed

- Claude Code's upgrade prompt is treated as a quota error, and unrecognized
  errors have a safe fallback.

## 0.2.0 - 2026-05-12

### Added

- `pedalpoint doctor` health checks and clearer error messages.
- Claude API fallback tier for when Claude Pro quota runs out.
- Junior and senior routing: structural tasks get a local draft that Claude
  reviews.

### Fixed

- The MCP server is registered with `claude mcp add`.

## 0.1.2 - 2026-05-11

### Fixed

- The skill installs to `~/.claude/skills/route-tasks/SKILL.md`.

## 0.1.1 - 2026-05-10

### Added

- PyPI releases through trusted publishing.

### Fixed

- The installer works through `curl | sh` and finds Python 3.11 to 3.13 when
  `python3` is too old.

## 0.1.0 - 2026-05-09

### Added

- First release: MCP server, `route-tasks` skill, circuit breaker and installer.
