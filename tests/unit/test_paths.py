from pathlib import Path

import pytest

from pedalpoint.paths import (
    draft_path_for,
    find_repo_root,
    parse_context_spec,
    resolve_in_repo,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "src").mkdir()
    return root.resolve()


def test_find_repo_root_from_nested_dir(repo: Path) -> None:
    nested = repo / "src" / "a" / "b"
    nested.mkdir(parents=True)
    assert find_repo_root(nested) == repo


def test_find_repo_root_git_file_worktree(tmp_path: Path) -> None:
    root = tmp_path / "wt"
    root.mkdir()
    (root / ".git").write_text("gitdir: /elsewhere\n")
    assert find_repo_root(root) == root.resolve()


def test_find_repo_root_none(tmp_path: Path) -> None:
    lonely = tmp_path / "nothing"
    lonely.mkdir()
    assert find_repo_root(lonely) is None


def test_resolve_relative_inside(repo: Path) -> None:
    assert resolve_in_repo("src/x.py", repo) == repo / "src" / "x.py"


def test_resolve_absolute_inside(repo: Path) -> None:
    assert resolve_in_repo(str(repo / "src" / "x.py"), repo) == repo / "src" / "x.py"


def test_resolve_root_itself(repo: Path) -> None:
    assert resolve_in_repo(".", repo) == repo


def test_resolve_dotdot_outside_raises(repo: Path) -> None:
    with pytest.raises(ValueError, match="outside the project repo"):
        resolve_in_repo("../x.py", repo)


def test_resolve_absolute_other_repo_raises(repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    (other / ".git").mkdir(parents=True)
    with pytest.raises(ValueError, match="outside the project repo"):
        resolve_in_repo(str(other / "x.py"), repo)


def test_resolve_symlink_escaping_repo_raises(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / "link").symlink_to(outside)
    with pytest.raises(ValueError, match="outside the project repo"):
        resolve_in_repo("link/x.py", repo)


def test_parse_context_spec_plain() -> None:
    assert parse_context_spec("a.py") == ("a.py", None, None)


def test_parse_context_spec_range() -> None:
    assert parse_context_spec("src/a.py:10-40") == ("src/a.py", 10, 40)


@pytest.mark.parametrize("spec", ["a.py:40-10", "a.py:0-3", "a.py:x-3"])
def test_parse_context_spec_bad_range_raises(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_context_spec(spec)


def test_draft_path_for() -> None:
    assert draft_path_for(Path("a/b.py")) == Path("a/b.py.draft")
