# Scenario: Draft Lands in the Worktree, Not the Main Checkout

## Setup
- Session opened in `~/dev/app` (main checkout); pedalpoint server pinned there
- Session then moves into worktree `~/dev/app-fix` (sibling) or `~/dev/app/.claude/worktrees/fix`
- Target `src/thing.py` differs between main and the worktree

## Expected Behavior
1. Skill calls `local_llm(..., target_path="src/thing.py", worktree="<worktree absolute path>")`
2. Server accepts it: same repository (shared `.git`)
3. Context and current contents are read from the worktree's files
4. `draft_path` is `<worktree>/src/thing.py.draft`; skill reviews and `mv`s it there

## Variants
- `worktree` points at a different repository → `… is not a worktree of …` →
  skill does the task itself; circuit unchanged
- `worktree` omitted (old skill) → draft goes to the main checkout (pre-0.5 behavior)

## Verification
- No `.draft` file appears in the main checkout
- `handoffs.jsonl` call record has `"repo"` = the worktree path
