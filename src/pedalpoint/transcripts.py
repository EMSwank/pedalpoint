"""Read real Claude token costs per handoff from Claude Code transcripts.

The transcript format (~/.claude/projects/<slug>/<session>.jsonl) is not a
published spec, so everything here tolerates missing fields and bad lines.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_HANDOFF_ID = re.compile(r'"handoff_id":\s*"([^"]+)"')
_CALL_TOOLS = ("__local_llm", "__claude_api")
_OUTCOME_TOOL = "__record_outcome"


@dataclass(frozen=True)
class HandoffCost:
    call_output: int
    review_output: int
    review_input: int
    complete: bool


def projects_dir() -> Path:
    return Path.home() / ".claude" / "projects"


def _entries(path: Path):
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except OSError:
        return
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            yield entry


def _blocks(entry: dict) -> list[dict]:
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict)]


def _result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def _scan(path: Path, wanted: set[str], found: dict[str, HandoffCost]) -> None:
    seen_requests: set[str] = set()
    open_: dict[str, list[int]] = {}  # hid -> [call_output, review_out, review_in]
    pending_calls: dict[str, int] = {}  # tool_use_id -> output of issuing request

    for entry in _entries(path):
        if entry.get("type") == "assistant":
            req = entry.get("requestId") or entry.get("uuid") or id(entry)
            message = entry.get("message")
            usage = message.get("usage") if isinstance(message, dict) else None
            usage = usage if isinstance(usage, dict) else {}
            out = int(usage.get("output_tokens") or 0)
            inp = sum(
                int(usage.get(k) or 0)
                for k in (
                    "input_tokens",
                    "cache_read_input_tokens",
                    "cache_creation_input_tokens",
                )
            )
            if req not in seen_requests:
                seen_requests.add(req)
                for totals in open_.values():
                    totals[1] += out
                    totals[2] += inp
            for block in _blocks(entry):
                if block.get("type") != "tool_use":
                    continue
                name = str(block.get("name", ""))
                if name.endswith(_CALL_TOOLS):
                    pending_calls[str(block.get("id"))] = out
                elif name.endswith(_OUTCOME_TOOL):
                    hid = (block.get("input") or {}).get("handoff_id")
                    if hid in open_:
                        call, rev_out, rev_in = open_.pop(hid)
                        found[hid] = HandoffCost(call, rev_out, rev_in, True)
        elif entry.get("type") == "user":
            for block in _blocks(entry):
                tool_id = block.get("tool_use_id")
                if block.get("type") != "tool_result" or tool_id not in pending_calls:
                    continue
                match = _HANDOFF_ID.search(_result_text(block))
                hid = match.group(1) if match else None
                if hid in wanted and hid not in found:
                    open_[hid] = [pending_calls[tool_id], 0, 0]

    for hid, (call, rev_out, rev_in) in open_.items():
        found.setdefault(hid, HandoffCost(call, rev_out, rev_in, False))


def handoff_costs(
    handoff_ids: set[str], root: Path | None = None
) -> dict[str, HandoffCost]:
    """Map each handoff id found in any transcript to its Claude token cost."""
    root = root or projects_dir()
    found: dict[str, HandoffCost] = {}
    if not root.is_dir() or not handoff_ids:
        return found
    for path in sorted(root.glob("*/*.jsonl")):
        _scan(path, handoff_ids, found)
    return found
