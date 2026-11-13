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
