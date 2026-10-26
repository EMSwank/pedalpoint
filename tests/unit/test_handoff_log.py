import json
from pathlib import Path

from pedalpoint import handoff_log


def test_log_path_under_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert handoff_log.log_path() == tmp_path / ".pedalpoint" / "handoffs.jsonl"


def test_append_creates_dir_and_appends(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "handoffs.jsonl"
    handoff_log.append({"kind": "call", "handoff_id": "a"}, path)
    handoff_log.append({"kind": "outcome", "handoff_id": "a", "score": 7}, path)
    lines = path.read_text().splitlines()
    assert [json.loads(line)["kind"] for line in lines] == ["call", "outcome"]


def test_append_default_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    handoff_log.append({"kind": "call", "handoff_id": "b"})
    assert handoff_log.read_all() == [{"kind": "call", "handoff_id": "b"}]


def test_read_all_missing_file_empty(tmp_path: Path) -> None:
    assert handoff_log.read_all(tmp_path / "nope.jsonl") == []


def test_read_all_skips_corrupt_line(tmp_path: Path) -> None:
    path = tmp_path / "handoffs.jsonl"
    path.write_text(
        '{"kind": "call", "handoff_id": "a"}\n'
        '{"kind": "ca\n'
        "\n"
        '["not", "a", "dict"]\n'
        '{"kind": "outcome", "handoff_id": "a"}\n'
    )
    records = handoff_log.read_all(path)
    assert [r["kind"] for r in records] == ["call", "outcome"]
