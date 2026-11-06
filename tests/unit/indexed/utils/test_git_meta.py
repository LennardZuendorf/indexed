"""Tests for the query-time git helper (``utils/git_meta``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

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

    # Same set minus the commit, proving the --cached leg is what finds a
    # staged-only path (a plain `git diff` cannot see it).
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


# ── line-level blame (#60) ──────────────────────────────────────────────────


def _blame_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """Two commits touching DIFFERENT lines: c1 writes lines 1-2, c2 edits line 2."""
    run_git(tmp_path, "init")
    (tmp_path / "code.py").write_text("first line\nsecond line\n")
    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-m", "c1", "--date=2026-01-01T00:00:00+00:00")
    first = run_git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    (tmp_path / "code.py").write_text("first line\nsecond line edited\n")
    run_git(
        tmp_path,
        "commit",
        "-am",
        "c2",
        "--author=Second Author <second@test.com>",
        "--date=2026-01-02T00:00:00+00:00",
    )
    second = run_git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    return tmp_path, first, second


def test_blame_lines_records_each_lines_own_commit(tmp_path: Path) -> None:
    repo, first, second = _blame_repo(tmp_path)

    lines = git_meta.blame_lines(str(repo), "code.py")
    assert lines is not None
    assert len(lines) == 2
    untouched, edited = lines[0], lines[1]
    assert untouched is not None and edited is not None
    assert untouched["commit"] == first
    assert edited["commit"] == second
    assert edited["author"] == "Second Author"
    assert edited["email"] == "second@test.com"
    assert edited["subject"] == "c2"
    assert edited["committedAt"].startswith("20")
    assert edited["uncommitted"] is False


def test_blame_lines_is_none_for_untracked_and_binary_paths(tmp_path: Path) -> None:
    repo, _first, _second = _blame_repo(tmp_path)
    (repo / "untracked.py").write_text("never committed\n")
    assert git_meta.blame_lines(str(repo), "untracked.py") is None
    assert git_meta.blame_lines(str(repo), "never-existed.py") is None

    (repo / "blob.bin").write_bytes(b"\x00\x01\x02binary")
    run_git(repo, "add", "blob.bin")
    run_git(repo, "commit", "-m", "binary")
    assert git_meta.blame_lines(str(repo), "blob.bin") is None


def test_resolve_range_maps_a_span_to_its_newest_touching_commit(
    tmp_path: Path,
) -> None:
    repo, first, second = _blame_repo(tmp_path)
    lines = git_meta.blame_lines(str(repo), "code.py")
    assert lines is not None

    # 0-based, inclusive — the code chunker's own convention.
    first_only = git_meta.resolve_range(lines, 0, 0)
    assert first_only is not None
    assert first_only["commit"] == first
    assert first_only["short"] == first[:7]
    assert first_only["author"] == "Test"
    assert first_only["email"] == "test@test.com"
    assert first_only["subject"] == "c1"
    assert first_only["committedAt"].startswith("20")
    assert (first_only["startLine"], first_only["endLine"]) == (1, 1)

    spanning = git_meta.resolve_range(lines, 0, 1)
    assert spanning is not None
    assert spanning["commit"] == second
    assert (spanning["startLine"], spanning["endLine"]) == (1, 2)


def test_resolve_range_marks_uncommitted_lines_instead_of_guessing(
    tmp_path: Path,
) -> None:
    repo, first, _second = _blame_repo(tmp_path)
    (repo / "code.py").write_text("first line\nsecond line edited\nlocal edit\n")

    lines = git_meta.blame_lines(str(repo), "code.py")
    assert lines is not None
    # A span that includes a working-tree line names that fact; it must never
    # report the committed ancestor as if it were line-level provenance.
    assert git_meta.resolve_range(lines, 0, 2) == {
        "uncommitted": True,
        "startLine": 1,
        "endLine": 3,
    }
    untouched = git_meta.resolve_range(lines, 0, 0)
    assert untouched is not None
    assert untouched["commit"] == first


def _blame_record(epoch: int, commit: str) -> Dict[str, Any]:
    return {
        "commit": commit,
        "short": commit[:7],
        "author": "A",
        "email": "a@b",
        "committedAt": "",
        "subject": "",
        "epoch": epoch,
        "uncommitted": False,
    }


def test_resolve_range_is_none_when_it_cannot_answer() -> None:
    assert git_meta.resolve_range(None, 0, 0) is None
    assert git_meta.resolve_range([], 0, 0) is None

    lines: List[Optional[Dict[str, Any]]] = [
        _blame_record(1, "a" * 40),
        None,
        _blame_record(2, "b" * 40),
    ]
    # A gap in the span is unanswerable — never filled with a neighbour's commit.
    assert git_meta.resolve_range(lines, 0, 2) is None
    tail = git_meta.resolve_range(lines, 2, 2)
    assert tail is not None
    assert tail["commit"] == "b" * 40
    # Out of the file's range (e.g. the file shrank after indexing).
    assert git_meta.resolve_range(lines, 0, 10) is None
    assert git_meta.resolve_range(lines, -1, 0) is None
    assert git_meta.resolve_range(lines, 2, 1) is None


def test_resolve_range_prefers_the_newest_commit_and_later_line_on_a_tie() -> None:
    lines: List[Optional[Dict[str, Any]]] = [
        _blame_record(10, "a" * 40),
        _blame_record(30, "b" * 40),
        _blame_record(30, "c" * 40),
    ]
    resolved = git_meta.resolve_range(lines, 0, 2)
    assert resolved is not None
    assert resolved["commit"] == "c" * 40
