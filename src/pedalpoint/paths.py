"""Path safety: keep every read and draft write inside the pinned project repo."""

from __future__ import annotations

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
