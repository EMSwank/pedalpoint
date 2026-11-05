"""Pure helpers for building draft prompts and sizing the result."""

from __future__ import annotations

import difflib
import math
import re
from pathlib import Path

MAX_EDIT_LINES = 300

# Thinking comes first in a reply; `<think>` later on may be the code itself.
_THINK = re.compile(r"\A\s*<think>.*?(?:</think>|\Z)", re.DOTALL)
# Real fences sit alone on their line; ``` inside a string literal does not.
_FENCE_LINE = re.compile(
    r"^```[\w+-]*[ \t]*\n(.*?)^```[ \t]*$", re.DOTALL | re.MULTILINE
)
_FENCE = re.compile(r"```[\w+-]*[ \t]*\n(.*?)```", re.DOTALL)
_OUTER_FENCE = re.compile(r"\A```[\w+-]*[ \t]*\n(.*)\n```\Z", re.DOTALL)
_PROSE_SUFFIXES = {".md", ".markdown", ".rst", ".txt"}


def is_prose_target(target: str) -> bool:
    """Docs keep their inner code blocks; only an outer wrapper fence is removed."""
    return Path(target).suffix.lower() in _PROSE_SUFFIXES


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def strip_output(text: str, prose_target: bool = False) -> str:
    """Drop thinking blocks, then unwrap the model's code.

    Code targets keep the longest fenced block (small models often wrap code in
    prose). Prose targets keep everything, minus one outer wrapper fence.
    """
    text = _THINK.sub("", text).strip()
    if prose_target:
        outer = _OUTER_FENCE.match(text)
        body = outer.group(1) if outer else text
    else:
        blocks = _FENCE_LINE.findall(text) or _FENCE.findall(text)
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
    old, new = original.splitlines(), draft.splitlines()
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    added = [
        line
        for tag, _, _, start, end in matcher.get_opcodes()
        if tag in ("replace", "insert")
        for line in new[start:end]
    ]
    return len(added), estimate_tokens("\n".join(added))
