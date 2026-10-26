import json
from pathlib import Path

from pedalpoint.transcripts import HandoffCost, handoff_costs, projects_dir


def _assistant(req: str, out: int, inp: int = 0, tools: list | None = None) -> dict:
    return {
        "type": "assistant",
        "requestId": req,
        "message": {
            "usage": {
                "input_tokens": inp,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "output_tokens": out,
            },
            "content": tools or [],
        },
    }


def _tool_use(tid: str, name: str, **inp) -> dict:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def _result(tid: str, text: str) -> dict:
    return {
        "type": "user",
        "message": {
            "content": [{"type": "tool_result", "tool_use_id": tid, "content": text}]
        },
    }


def _write(root: Path, entries: list, name: str = "s1.jsonl") -> None:
    proj = root / "-Users-me-proj"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / name).write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def _session(hid: str = "h1") -> list:
    return [
        _assistant("r0", 500, 9999),  # before the handoff — never counted
        _assistant("r1", 80, 10, [_tool_use("t1", "mcp__pedalpoint__local_llm")]),
        _result("t1", json.dumps({"handoff_id": hid, "draft_path": "x.draft"})),
        _assistant("r2", 40, 1000),
        _assistant("r3", 30, 1000),
        _assistant(
            "r4",
            20,
            500,
            [_tool_use("t2", "mcp__pedalpoint__record_outcome", handoff_id=hid)],
        ),
        _assistant("r5", 700, 9999),  # after outcome — never counted
    ]


def test_projects_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert projects_dir() == tmp_path / ".claude" / "projects"


def test_single_handoff_costs(tmp_path: Path) -> None:
    _write(tmp_path, _session())
    assert handoff_costs({"h1"}, tmp_path) == {
        "h1": HandoffCost(
            call_output=80, review_output=90, review_input=2500, complete=True
        )
    }


def test_split_request_counted_once(tmp_path: Path) -> None:
    entries = _session()
    entries.insert(4, _assistant("r2", 40, 1000))  # same requestId, second line
    _write(tmp_path, entries)
    assert handoff_costs({"h1"}, tmp_path)["h1"].review_output == 90


def test_cache_tokens_count_as_input(tmp_path: Path) -> None:
    entries = _session()
    entries[3]["message"]["usage"]["cache_read_input_tokens"] = 5000
    _write(tmp_path, entries)
    assert handoff_costs({"h1"}, tmp_path)["h1"].review_input == 7500


def test_unclosed_handoff_incomplete(tmp_path: Path) -> None:
    _write(tmp_path, _session()[:4])
    cost = handoff_costs({"h1"}, tmp_path)["h1"]
    assert cost.complete is False
    assert cost.review_output == 40


def test_unknown_ids_ignored(tmp_path: Path) -> None:
    _write(tmp_path, _session("other"))
    assert handoff_costs({"h1"}, tmp_path) == {}


def test_corrupt_line_skipped(tmp_path: Path) -> None:
    _write(tmp_path, _session())
    path = tmp_path / "-Users-me-proj" / "s1.jsonl"
    path.write_text("{broken\n" + path.read_text() + "[1, 2]\n")
    assert handoff_costs({"h1"}, tmp_path)["h1"].complete is True


def test_missing_projects_dir_empty(tmp_path: Path) -> None:
    assert handoff_costs({"h1"}, tmp_path / "nope") == {}


def test_tool_result_as_content_blocks(tmp_path: Path) -> None:
    entries = _session()
    entries[2]["message"]["content"][0]["content"] = [
        {"type": "text", "text": json.dumps({"handoff_id": "h1"})}
    ]
    _write(tmp_path, entries)
    assert handoff_costs({"h1"}, tmp_path)["h1"].call_output == 80


def test_two_overlapping_handoffs(tmp_path: Path) -> None:
    entries = [
        _assistant("r1", 80, 0, [_tool_use("t1", "mcp__pedalpoint__local_llm")]),
        _result("t1", '{"handoff_id": "a"}'),
        _assistant("r2", 60, 0, [_tool_use("t2", "mcp__pedalpoint__claude_api")]),
        _result("t2", '{"handoff_id": "b"}'),
        _assistant("r3", 10, 0),
        _assistant(
            "r4",
            5,
            0,
            [_tool_use("t3", "mcp__pedalpoint__record_outcome", handoff_id="a")],
        ),
        _assistant(
            "r5",
            7,
            0,
            [_tool_use("t4", "mcp__pedalpoint__record_outcome", handoff_id="b")],
        ),
    ]
    _write(tmp_path, entries)
    costs = handoff_costs({"a", "b"}, tmp_path)
    assert costs["a"] == HandoffCost(80, 60 + 10 + 5, 0, True)
    assert costs["b"] == HandoffCost(60, 10 + 5 + 7, 0, True)


def test_malformed_entries_tolerated(tmp_path: Path) -> None:
    entries = _session()
    entries[1:1] = [
        {"type": "assistant", "requestId": "x1", "message": "not a dict"},
        {"type": "user", "message": {"content": "plain string"}},
        _assistant("x2", 0, 0, [{"type": "text", "text": "hi"}]),
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "zz", "content": "x"},
                    {"type": "tool_result", "tool_use_id": "t1", "content": None},
                ]
            },
        },
    ]
    _write(tmp_path, entries)
    (tmp_path / "-Users-me-proj" / "dir.jsonl").mkdir()  # unreadable as a file
    assert handoff_costs({"h1"}, tmp_path)["h1"] == HandoffCost(80, 90, 2500, True)
