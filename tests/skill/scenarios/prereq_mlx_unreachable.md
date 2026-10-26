# Scenario: Prerequisites — MLX Server Not Running

## Setup
- PEDALPOINT_BACKEND=mlx; `mlx_lm.server` not running
- pedalpoint MCP server connected

## Expected Behavior
1. Skill calls `local_llm_status`
2. Result: `{"backend": "mlx", "model": "mlx-community/gemma-4-e4b-it-4bit", "reachable": false, ...}`
3. Skill prints: `⚠ MLX unreachable — start it with: mlx_lm.server --model mlx-community/gemma-4-e4b-it-4bit`
4. All tasks fall back to Agent

## Variants
- backend ollama, unreachable → hint is `ollama serve`
- Result has no `server_version` key (older server) → also print
  `⚠ pedalpoint server is older than this skill — re-run install.sh`
- `repo_root` is null → print a note that local handoffs need a git repo; all tasks to Agent
- `local_llm` is listed but `local_llm_status` is not (0.3 server with 0.4 skill) →
  print `⚠ pedalpoint server is older than this skill — re-run install.sh`, all tasks to Agent
