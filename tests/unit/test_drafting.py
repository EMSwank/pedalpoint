from pedalpoint.drafting import (
    MAX_EDIT_LINES,
    build_prompt,
    change_size,
    estimate_tokens,
    strip_output,
)


def test_max_edit_lines() -> None:
    assert MAX_EDIT_LINES == 300


def test_estimate_tokens() -> None:
    assert estimate_tokens("abcde") == 2
    assert estimate_tokens("") == 0


def test_strip_output_removes_think_and_fence() -> None:
    assert strip_output("<think>x</think>\n```python\nprint(1)\n```") == "print(1)\n"


def test_strip_output_longest_fence_wins() -> None:
    text = "```\na\n```\nprose\n```py\nb = 1\nc = 2\n```"
    assert strip_output(text) == "b = 1\nc = 2\n"


def test_strip_output_plain_text() -> None:
    assert strip_output("  x = 1\n\n") == "x = 1\n"


def test_strip_output_empty() -> None:
    assert strip_output("<think>a\nb</think>") == ""


def test_build_prompt_order() -> None:
    prompt = build_prompt(
        "add y",
        [("a.py lines 1-3", "x = 1")],
        "t.py",
        "old = 1\n",
    )
    assert (
        prompt.index("## Context: a.py lines 1-3")
        < prompt.index("## Current contents of t.py")
        < prompt.index("## Task")
    )
    assert "x = 1" in prompt and "old = 1" in prompt and "add y" in prompt
    assert prompt.endswith("Output the complete contents of t.py.")


def test_build_prompt_new_file_has_no_current_section() -> None:
    prompt = build_prompt("make it", [], "new.py", None)
    assert "## Current contents" not in prompt
    assert prompt.endswith("Output the complete contents of new.py.")


def test_change_size_new_file() -> None:
    assert change_size(None, "a\nb\n") == (2, estimate_tokens("a\nb\n"))


def test_change_size_edit_counts_only_changed() -> None:
    original = "".join(f"line {i}\n" for i in range(100))
    draft = original + "extra 1\nextra 2\n"
    lines, tokens = change_size(original, draft)
    assert lines == 2
    assert tokens == estimate_tokens("extra 1\nextra 2")


def test_change_size_replaced_line_counts() -> None:
    lines, _ = change_size("a\nb\nc\n", "a\nB\nc\n")
    assert lines == 1


def test_change_size_identical() -> None:
    assert change_size("a\nb\n", "a\nb\n") == (0, 0)
