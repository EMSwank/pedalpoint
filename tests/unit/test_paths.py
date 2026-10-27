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


def test_write_draft_replaces_symlink_without_following(tmp_path: Path) -> None:
    from pedalpoint.paths import write_draft

    outside = tmp_path / "outside.txt"
    outside.write_text("keep\n")
    draft = tmp_path / "a.py.draft"
    draft.symlink_to(outside)
    write_draft(draft, "new\n")
    assert outside.read_text() == "keep\n"
    assert not draft.is_symlink() and draft.read_text() == "new\n"


def test_write_draft_overwrites_regular_file(tmp_path: Path) -> None:
    from pedalpoint.paths import write_draft

    draft = tmp_path / "a.py.draft"
    draft.write_text("old\n")
    write_draft(draft, "new\n")
    assert draft.read_text() == "new\n"


# ── worktrees of the pinned repo ────────────────────────────────────────────


def _git(*args: str, cwd: Path) -> None:
    import subprocess

    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A real repo with a sibling worktree and one under .claude/worktrees."""
    main = tmp_path / "main"
    main.mkdir()
    _git("init", "-q", cwd=main)
    (main / "a.py").write_text("x = 1\n")
    _git("add", ".", cwd=main)
    _git("commit", "-qm", "init", cwd=main)
    _git("worktree", "add", "-q", "../sibling", "-b", "sib", cwd=main)
    _git("worktree", "add", "-q", ".claude/worktrees/inner", "-b", "inner", cwd=main)
    return main.resolve()


def test_git_common_dir_same_for_all_worktrees(git_repo: Path) -> None:
    from pedalpoint.paths import git_common_dir

    expected = git_repo / ".git"
    assert git_common_dir(git_repo) == expected
    assert git_common_dir(git_repo.parent / "sibling") == expected
    assert git_common_dir(git_repo / ".claude/worktrees/inner") == expected


def test_git_common_dir_unreadable_git_file(tmp_path: Path) -> None:
    from pedalpoint.paths import git_common_dir

    (tmp_path / ".git").write_text("not a gitdir line\n")
    assert git_common_dir(tmp_path) is None


def test_select_root_defaults_to_pinned(git_repo: Path) -> None:
    from pedalpoint.paths import select_root

    assert select_root(git_repo, None) == git_repo
    assert select_root(None, None) is None


@pytest.mark.parametrize("where", ["sibling", "main/.claude/worktrees/inner"])
def test_select_root_accepts_worktree_of_pinned_repo(
    git_repo: Path, where: str
) -> None:
    from pedalpoint.paths import select_root

    wt = git_repo.parent / where
    (wt / "src").mkdir()
    assert select_root(git_repo, str(wt)) == wt
    assert select_root(git_repo, str(wt / "src")) == wt


def test_select_root_rejects_other_repo(git_repo: Path, tmp_path: Path) -> None:
    from pedalpoint.paths import select_root

    other = tmp_path / "other"
    other.mkdir()
    _git("init", "-q", cwd=other)
    with pytest.raises(ValueError, match="is not a worktree of"):
        select_root(git_repo, str(other))


def test_select_root_rejects_non_git_dir(git_repo: Path, tmp_path: Path) -> None:
    from pedalpoint.paths import select_root

    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(ValueError, match="is not inside a git worktree"):
        select_root(git_repo, str(plain))


def test_select_root_needs_a_pinned_repo(tmp_path: Path) -> None:
    from pedalpoint.paths import select_root

    with pytest.raises(ValueError, match="Not in a git repository"):
        select_root(None, str(tmp_path))


def test_git_common_dir_missing_git(tmp_path: Path) -> None:
    from pedalpoint.paths import git_common_dir

    assert git_common_dir(tmp_path) is None


def test_git_common_dir_gitdir_without_commondir(tmp_path: Path) -> None:
    from pedalpoint.paths import git_common_dir

    (tmp_path / "real").mkdir()
    (tmp_path / "wt").mkdir()
    (tmp_path / "wt" / ".git").write_text("gitdir: ../real\n")
    assert git_common_dir(tmp_path / "wt") == (tmp_path / "real").resolve()
