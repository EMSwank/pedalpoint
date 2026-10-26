"""Append-only JSONL log of local handoffs (`~/.pedalpoint/handoffs.jsonl`).

Record kinds:
- call:    handoff_id, ts, repo, backend, model, target, draft_path, lines,
           lines_changed, changed_tokens, prompt_tokens, completion_tokens, seconds
- outcome: handoff_id, ts, score (1-7), note
"""

from __future__ import annotations

import json
from pathlib import Path


def log_path() -> Path:
    return Path.home() / ".pedalpoint" / "handoffs.jsonl"


def append(record: dict, path: Path | None = None) -> None:
    path = path or log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def read_all(path: Path | None = None) -> list[dict]:
    """Return every parseable record; blank or corrupt lines are skipped."""
    path = path or log_path()
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records
