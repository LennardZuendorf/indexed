"""Tests for the query-time git helper (``utils/git_meta``)."""

from __future__ import annotations

import time
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


def _recorded_mtime(path: Path) -> str:
    """The ISO value the files reader writes onto a node for ``path``."""
    from indexed.connectors.files.files_document_reader import FilesDocumentReader

    return FilesDocumentReader._read_file_modification_time(str(path)).isoformat()


def test_snapshot_is_current_compares_the_recorded_mtime(tmp_path: Path) -> None:
    """Provenance may only ride a snapshot that still matches the file on disk."""
    import time

    (tmp_path / "a.txt").write_text("indexed text")
    current = _recorded_mtime(tmp_path / "a.txt")

    # Writer convention: offset-aware, so the string is self-describing.
    assert current.endswith("+00:00")
    assert git_meta.snapshot_is_current(str(tmp_path), "a.txt", current) is True
    assert (
        git_meta.snapshot_is_current(
            str(tmp_path), "a.txt", "2000-01-01T00:00:00+00:00"
        )
        is False
    )
    assert git_meta.snapshot_is_current(str(tmp_path), "gone.txt", current) is False

    # An aware value still bites after a real mtime change (the ``touch`` case).
    time.sleep(0.01)
    (tmp_path / "a.txt").touch()
    assert git_meta.snapshot_is_current(str(tmp_path), "a.txt", current) is False


def test_snapshot_is_current_judges_legacy_naive_values_against_index_time(
    tmp_path: Path,
) -> None:
    """Offset-less values cannot be zoned, so they are judged by index time.

    The old writers stored naive LOCAL wall time; parsing it in the reader's zone
    is the #279 B1 defect. The zone-free answer is "not newer than the index".
    """
    import datetime

    path = tmp_path / "a.txt"
    path.write_text("indexed text")
    legacy = datetime.datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    assert legacy.endswith("+00:00") is False  # genuinely offset-less

    indexed_at = datetime.datetime.now(datetime.timezone.utc)
    assert git_meta.snapshot_is_current(
        str(tmp_path), "a.txt", legacy, indexed_at.isoformat()
    )
    # Missing timestamp takes the same path: degrade towards provenance present.
    assert git_meta.snapshot_is_current(
        str(tmp_path), "a.txt", None, indexed_at.isoformat()
    )
    # No anchor either: still degrade towards present, never silently dark.
    assert git_meta.snapshot_is_current(str(tmp_path), "a.txt", legacy)

    # Indexed an hour ago, touched since: the file is newer than the index.
    past = (indexed_at - datetime.timedelta(hours=1)).isoformat()
    assert not git_meta.snapshot_is_current(str(tmp_path), "a.txt", legacy, past)


def test_snapshot_is_current_is_zone_independent_across_processes(
    tmp_path: Path,
) -> None:
    """The #279 B1 repro: write under one zone, read under another.

    A different TZ in a different PROCESS is what breaks the naive round-trip;
    a same-interpreter test can pass against the buggy code.
    """
    import json
    import os
    import subprocess
    import sys

    path = tmp_path / "a.txt"
    path.write_text("indexed text")

    writer = (
        "import json,os,sys\n"
        "from indexed.connectors.files.files_document_reader import FilesDocumentReader\n"
        "p=sys.argv[1]\n"
        "print(json.dumps({'modified_time':"
        "FilesDocumentReader._read_file_modification_time(p).isoformat(),"
        "'mtime':os.path.getmtime(p)}))\n"
    )
    env = dict(os.environ, TZ="Europe/Stockholm")
    written = json.loads(
        subprocess.run(
            [sys.executable, "-c", writer, str(path)],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        ).stdout
    )

    reader = (
        "import datetime,json,os,sys\n"
        "from indexed.utils import git_meta\n"
        "d=json.loads(sys.argv[1]); p=sys.argv[2]\n"
        "recorded=datetime.datetime.fromisoformat(d['modified_time'])\n"
        "print(json.dumps({"
        "'current':git_meta.snapshot_is_current(os.path.dirname(p),"
        "os.path.basename(p),d['modified_time'],d.get('indexed_at')),"
        "'delta_s':recorded.timestamp()-d['mtime'],"
        "'aware':recorded.tzinfo is not None}))\n"
    )

    for read_zone in ("UTC", "America/New_York"):
        env = dict(os.environ, TZ=read_zone)
        os.utime(path, (written["mtime"], written["mtime"]))
        out = json.loads(
            subprocess.run(
                [sys.executable, "-c", reader, json.dumps(written), str(path)],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            ).stdout
        )
        assert out["aware"] is True
        assert out["delta_s"] == pytest.approx(0.0, abs=1e-3)
        assert out["current"] is True

        # ``touch``: content unchanged, mtime moved — provenance must go dark
        # under the same cross-process read, exactly as it does in one zone.
        os.utime(path, (written["mtime"] + 5.0, written["mtime"] + 5.0))
        out = json.loads(
            subprocess.run(
                [sys.executable, "-c", reader, json.dumps(written), str(path)],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            ).stdout
        )
        assert out["current"] is False


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


# ── scoring inputs for the git-signal re-rank (#144) ───────────────────────


def test_newest_touch_keeps_the_epoch_of_the_span_newest_line() -> None:
    lines: List[Optional[Dict[str, Any]]] = [
        _blame_record(10, "a" * 40),
        _blame_record(99, "b" * 40),
        _blame_record(50, "c" * 40),
    ]

    whole = git_meta.newest_touch(lines)
    assert whole is not None
    assert whole["epoch"] == 99
    assert whole["uncommitted"] is False

    second = git_meta.newest_touch(lines, 1, 1)
    assert second is not None
    assert second["epoch"] == 99
    # A span that no longer fits the file (it shrank) falls back to the file's
    # newest line rather than inventing a span.
    assert git_meta.newest_touch(lines, 5, 9)["epoch"] == 99  # type: ignore[index]


def test_newest_touch_flags_a_working_tree_line_as_freshest() -> None:
    dirty = dict(_blame_record(10, "a" * 40))
    dirty.update({"uncommitted": True, "commit": "0" * 40})

    touch = git_meta.newest_touch([_blame_record(999, "b" * 40), dirty])
    assert touch is not None
    assert touch["uncommitted"] is True
    assert touch["epoch"] is None


def test_newest_touch_is_none_when_blame_cannot_answer() -> None:
    assert git_meta.newest_touch(None) is None
    assert git_meta.newest_touch([]) is None
    assert git_meta.newest_touch([None, None]) is None


def test_recent_commit_count_counts_commits_since_and_none_outside_a_repo(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    (tmp_path / "a.txt").write_text("one")
    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-m", "old", "--date=2020-01-01T00:00:00+00:00")
    (tmp_path / "a.txt").write_text("two")
    run_git(tmp_path, "commit", "-am", "new")

    # Since the epoch is "everything" — both commits count.
    assert git_meta.recent_commit_count(str(tmp_path), "a.txt", 0) == 2
    # A window that starts after every commit is a real zero, not unknown.
    assert (
        git_meta.recent_commit_count(str(tmp_path), "a.txt", int(time.time()) + 86_400)
        == 0
    )
    # An untracked path is a real zero.
    assert git_meta.recent_commit_count(str(tmp_path), "nope.txt", 0) == 0
    # Outside a repo git cannot answer at all.
    assert git_meta.recent_commit_count(str(tmp_path / "none"), "a.txt", 0) is None


def test_rerank_skip_message_names_known_and_unknown_reasons() -> None:
    message = git_meta.rerank_skip_message({"reason": "no-git-repository"})
    assert "no git repository" in message
    assert "similarity only" in message
    # An unrecognized code is passed through, never hidden.
    assert "brand-new-reason" in git_meta.rerank_skip_message(
        {"reason": "brand-new-reason"}
    )


def test_git_paths_preserve_utf8_whitespace_and_newlines(git_repo, monkeypatch):
    from tests.conftest import run_git

    names = [" café ", "line\nbreak.txt", " trailing "]
    for name in names:
        (git_repo / name).write_text("one", encoding="utf-8")
    run_git(git_repo, "add", "--", *names)
    run_git(git_repo, "commit", "-m", "écriture")
    for name in names:
        (git_repo / name).write_text("two", encoding="utf-8")
    (git_repo / " untracked\n ").write_text("new", encoding="utf-8")
    monkeypatch.setenv("LC_ALL", "C")
    assert set(names) | {" untracked\n "} <= git_meta.changed_paths(
        str(git_repo), "HEAD"
    )
    assert git_meta.last_commit(str(git_repo), names[0])["subject"] == "écriture"


def test_history_uses_literal_path_and_committer_date(git_repo):
    from tests.conftest import run_git
    import os
    import subprocess

    literal = git_repo / "note[1].md"
    literal.write_text("literal\n")
    run_git(git_repo, "add", "--", "note[1].md")
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2020-01-01T00:00:00+0000",
        "GIT_COMMITTER_DATE": "2022-01-01T00:00:00+0000",
    }
    subprocess.run(
        [
            "git",
            "-C",
            str(git_repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@test.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-m",
            "literal",
        ],
        env=env,
        check=True,
        capture_output=True,
    )
    expected = run_git(git_repo, "rev-parse", "HEAD").stdout.strip()
    (git_repo / "note1.md").write_text("other\n")
    run_git(git_repo, "add", "--", "note1.md")
    run_git(git_repo, "commit", "-m", "other")
    info = git_meta.last_commit(str(git_repo), "note[1].md")
    assert info["commit"] == expected
    assert info["committedAt"].startswith("2022-01-01")
    line = git_meta.blame_lines(str(git_repo), "note[1].md")[0]
    assert line["committedAt"].startswith("2022-01-01")
    assert line["epoch"] == 1577836800
    assert git_meta.recent_commit_count(str(git_repo), "note[1].md", 0) == 1


def test_git_subprocess_explicit_utf8(monkeypatch, git_repo):
    import subprocess

    original = subprocess.run
    observed = []

    def spy(*args, **kwargs):
        observed.append(kwargs.get("encoding"))
        return original(*args, **kwargs)

    monkeypatch.setattr(git_meta.subprocess, "run", spy)
    assert git_meta.head_commit(str(git_repo))
    assert observed == ["utf-8"]
