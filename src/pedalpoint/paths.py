"""Path safety: keep every read and draft write inside the pinned project repo."""

from __future__ import annotations

import os
import re
from pathlib import Path

_RANGE = re.compile(r"^(?P<path>.+):(?P<start>\w+)-(?P<end>\w+)$")


def find_repo_root(start: Path) -> Path | None:
    """Return the nearest ancestor containing `.git` (dir or worktree file)."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def git_common_dir(root: Path) -> Path | None:
    """The `.git` directory every worktree of `root`'s repository shares."""
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git.resolve()
    try:
        line = dot_git.read_text().strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    gitdir = (root / line.removeprefix("gitdir:").strip()).resolve()
    try:
        common = (gitdir / "commondir").read_text().strip()
    except OSError:
        return gitdir
    return (gitdir / common).resolve()


def select_root(pinned: Path | None, worktree: str | None) -> Path | None:
    """The repo root for one call: the pinned repo, or a worktree of it.

    The server pins the repo it started in; a session that later moves into a
    worktree names it here. Any worktree of the same repository is allowed
    (same shared `.git`); anything else is refused.
    """
    if worktree is None:
        return pinned
    if pinned is None:
        raise ValueError("Not in a git repository — local_llm needs a project repo")
    root = find_repo_root(Path(worktree))
    if root is None:
        raise ValueError(f"{worktree!r} is not inside a git worktree")
    common = git_common_dir(root)
    if common is None or common != git_common_dir(pinned):
        raise ValueError(f"{worktree!r} is not a worktree of {pinned}")
    return root


def resolve_in_repo(raw: str, root: Path) -> Path:
    """Resolve `raw` (relative to `root`), following symlinks; reject escapes."""
    root = root.resolve()
    resolved = (root / raw).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"Path {raw!r} is outside the project repo {root}")
    return resolved


def parse_context_spec(spec: str) -> tuple[str, int | None, int | None]:
    """Split `path` or `path:START-END` (1-indexed, inclusive)."""
    match = _RANGE.match(spec)
    if not match:
        return spec, None, None
    start, end = match["start"], match["end"]
    if not (start.isdigit() and end.isdigit()):
        raise ValueError(f"Bad line range in {spec!r}")
    first, last = int(start), int(end)
    if first < 1 or last < first:
        raise ValueError(f"Bad line range in {spec!r}")
    return match["path"], first, last


def draft_path_for(target: Path) -> Path:
    return target.with_name(target.name + ".draft")


def write_draft(draft: Path, text: str) -> None:
    """Write a fresh regular file; never follow a symlink or hard link at `draft`."""
    if draft.is_symlink() or draft.exists():
        draft.unlink()
    fd = os.open(draft, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
