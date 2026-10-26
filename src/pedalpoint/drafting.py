"""Pure helpers for building draft prompts and sizing the result."""

from __future__ import annotations

import difflib
import math
import re

MAX_EDIT_LINES = 300

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE = re.compile(r"```[\w+-]*[ \t]*\n(.*?)```", re.DOTALL)


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def strip_output(text: str) -> str:
    """Drop thinking blocks; keep the longest fenced block, else the plain text."""
    text = _THINK.sub("", text)
    blocks = _FENCE.findall(text)
    body = max(blocks, key=len) if blocks else text
    body = body.strip()
    return body + "\n" if body else ""


def build_prompt(
    task: str,
    context: list[tuple[str, str]],
    target_rel: str,
    existing: str | None,
) -> str:
    sections = [f"## Context: {label}\n```\n{text}\n```" for label, text in context]
    if existing is not None:
        sections.append(f"## Current contents of {target_rel}\n```\n{existing}\n```")
    sections.append(f"## Task\n{task}\n\nOutput the complete contents of {target_rel}.")
    return "\n\n".join(sections)


def change_size(original: str | None, draft: str) -> tuple[int, int]:
    """Return (lines_changed, changed_tokens) — what Claude would have written."""
    if original is None:
        return len(draft.splitlines()), estimate_tokens(draft)
    added = [
        line[2:]
        for line in difflib.ndiff(original.splitlines(), draft.splitlines())
        if line.startswith("+ ")
    ]
    return len(added), estimate_tokens("\n".join(added))
