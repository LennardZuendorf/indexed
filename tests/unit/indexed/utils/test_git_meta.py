"""Tests for the query-time git helper (``utils/git_meta``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from indexed.utils import git_meta
from tests.conftest import run_git

pytestmark = pytest.mark.unit


def _two_commit_repo(tmp_path: Path) -> Path:
    """Repo: c1 tracks initial/stable, c2 adds touched.txt, then dirty work."""
    run_git(tmp_path, "init")
    (tmp_path / "initial.txt").write_text("initial")
    (tmp_path / "stable.txt").write_text("stable")
    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-m", "c1")
    (tmp_path / "touched.txt").write_text("touched")
    run_git(tmp_path, "add", "touched.txt")
    run_git(tmp_path, "commit", "-m", "c2 touch")
    # One of each kind of uncommitted change on top of c2.
    (tmp_path / "staged.txt").write_text("staged")
    run_git(tmp_path, "add", "staged.txt")
    (tmp_path / "initial.txt").write_text("initial edited")
    (tmp_path / "untracked.txt").write_text("untracked")
    return tmp_path


def test_non_repo_is_all_none(tmp_path: Path) -> None:
    assert git_meta.repo_toplevel(str(tmp_path)) is None
    assert git_meta.is_git_repo(str(tmp_path)) is False
    assert git_meta.changed_paths(str(tmp_path), "HEAD") is None
    assert git_meta.last_commit(str(tmp_path), "a.txt") is None


def test_repo_toplevel_resolves_a_nested_path(git_repo: Path) -> None:
    nested = git_repo / "sub" / "dir"
    nested.mkdir(parents=True)
    assert git_meta.repo_toplevel(str(nested)) == str(git_repo)
    assert git_meta.is_git_repo(str(nested)) is True


def test_changed_paths_covers_committed_staged_unstaged_untracked(
    tmp_path: Path,
) -> None:
    repo = _two_commit_repo(tmp_path)

    since_c1 = git_meta.changed_paths(str(repo), "HEAD~1")
    assert since_c1 is not None
    assert since_c1 == {
        "touched.txt",  # committed after the ref
        "staged.txt",  # staged only
        "initial.txt",  # unstaged only
        "untracked.txt",  # neither tracked nor staged
    }
    assert "stable.txt" not in since_c1

    # The same set minus the commit. A staged-only path is found by the single
    # ``git diff <ref> --`` leg: it compares REF's tree with the WORKING TREE,
    # so no ``--cached`` / unstaged leg is needed.
    assert git_meta.changed_paths(str(repo), "HEAD") == {
        "staged.txt",
        "initial.txt",
        "untracked.txt",
    }


def test_changed_paths_invalid_ref_is_none_not_empty(tmp_path: Path) -> None:
    repo = _two_commit_repo(tmp_path)
    assert git_meta.changed_paths(str(repo), "no-such-ref") is None
    # HEAD is valid but HEAD~99 is not: a typo must never look like "no changes".
    assert git_meta.changed_paths(str(repo), "HEAD~99") is None


@pytest.mark.parametrize(
    "ref",
    ["--upload-pack=touch /tmp/x", "; rm -rf /tmp/x", "--output=/tmp/x", "a" * 500],
)
def test_changed_paths_rejects_option_shaped_and_metacharacter_refs(
    tmp_path: Path, ref: str
) -> None:
    """The ref is one argv element behind a ``rev-parse --verify`` gate.

    A later refactor to ``shell=True`` or a dropped ``--`` must fail here
    instead of shipping an injection (#279 review, finding 3).
    """
    repo = _two_commit_repo(tmp_path)
    assert git_meta.changed_paths(str(repo), ref) is None


def test_last_commit_reports_the_touching_commit(tmp_path: Path) -> None:
    repo = _two_commit_repo(tmp_path)
    commit = git_meta.last_commit(str(repo), "touched.txt")
    assert commit is not None
    assert commit["author"] == "Test"
    assert commit["email"] == "test@test.com"
    assert commit["subject"] == "c2 touch"
    assert len(commit["commit"]) == 40
    assert commit["commit"].startswith(commit["short"])
    assert commit["committedAt"].startswith("20")

    assert git_meta.last_commit(str(repo), "untracked.txt") is None
    assert git_meta.last_commit(str(repo), "never-existed.txt") is None


def test_repo_relative_rebases_a_nested_base_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    base = repo / "sub" / "dir"
    assert git_meta.repo_relative(str(repo), str(base), "note.md") == "sub/dir/note.md"


def test_repo_relative_keeps_a_space_in_the_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    base = repo / "docs dir"
    assert (
        git_meta.repo_relative(str(repo), str(base), "my file.md")
        == "docs dir/my file.md"
    )


def test_snapshot_is_current_compares_the_recorded_mtime(tmp_path: Path) -> None:
    """Provenance may only ride a snapshot that still matches the file on disk."""
    from datetime import datetime

    (tmp_path / "a.txt").write_text("indexed text")
    current = datetime.fromtimestamp((tmp_path / "a.txt").stat().st_mtime).isoformat()

    assert git_meta.snapshot_is_current(str(tmp_path), "a.txt", current) is True
    assert git_meta.snapshot_is_current(str(tmp_path), "a.txt", "2000-01-01T00:00:00") is False
    assert git_meta.snapshot_is_current(str(tmp_path), "a.txt", None) is False
    assert git_meta.snapshot_is_current(str(tmp_path), "gone.txt", current) is False
