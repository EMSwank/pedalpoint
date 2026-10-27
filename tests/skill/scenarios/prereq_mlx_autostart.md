# Scenario: Prerequisites — MLX Not Running, Autostart On

## Setup
- PEDALPOINT_BACKEND=mlx (autostart on by default); `mlx_lm.server` not running
- pedalpoint MCP server connected, inside a git repo

## Expected Behavior
1. Skill calls `local_llm_status`
2. Result: `{"backend": "mlx", "reachable": false, "autostart": true, "idle_minutes": 20, ...}`
3. Skill prints no warning and keeps the local path enabled
4. First structural task: `local_llm` takes ~10s longer (model load), returns a draft as usual
5. Later tasks: normal speed

## Variants
- First `local_llm` returns `MLX server did not start within 120s — see …/mlx.log` →
  skill prints the error and does that task itself; circuit unchanged
- `mlx_lm.server not found` → skill prints the error (contains `uv tool install mlx-lm`),
  does the task itself; circuit unchanged

## Verification
- No `⚠ MLX unreachable` line at startup
- state.json unchanged by any autostart error
