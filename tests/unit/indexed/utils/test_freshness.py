"""Index freshness reporting (#146 slice 1): verdicts, reasons, real git facts.

Every case runs against a real temporary repository — no mocked git — because
the whole point is an honest answer about actual history, and a mock cannot
tell a rewritten history from a clean tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import xxhash

from indexed.connectors.files.change_tracker import ChangeTracker
from indexed.utils import freshness
from tests.conftest import run_git

pytestmark = pytest.mark.unit


def _sha(repo: Path, rev: str = "HEAD") -> str:
    return run_git(repo, "rev-parse", rev).stdout.strip()


def _hashes(source: Path, *names: str) -> dict[str, str]:
    return {
        name: xxhash.xxh64((source / name).read_bytes()).hexdigest() for name in names
    }


def _evaluate(
    source: Path,
    baseline: tuple[str | None, dict[str, str] | None],
    reader_type: str = "localFiles",
) -> freshness.Freshness:
    commit, hashes = baseline
    return freshness.evaluate(
        reader_type=reader_type,
        source_path=str(source),
        baseline_commit=commit,
        indexed_hashes=hashes,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """One commit tracking ``a.txt``; the source root IS the repo root.

    Lives one level below ``tmp_path`` so a test can create a collection
    directory beside it (an untracked dir inside the repo would legitimately
    make the index stale).
    """
    root = tmp_path / "repo"
    root.mkdir()
    run_git(root, "init")
    (root / "a.txt").write_text("a")
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "c1")
    return root


def test_clean_worktree_is_fresh(repo: Path) -> None:
    verdict = _evaluate(repo, (_sha(repo), _hashes(repo, "a.txt")))
    assert verdict.status == freshness.FRESH
    assert verdict.reason is None
    assert verdict.summary() == "fresh — the index matches the working tree"


def test_modified_file_is_stale_and_counted(repo: Path) -> None:
    baseline = (_sha(repo), _hashes(repo, "a.txt"))
    (repo / "a.txt").write_text("edited after indexing")
    verdict = _evaluate(repo, baseline)
    assert verdict.status == freshness.STALE
    assert verdict.reason == freshness.SOURCE_CHANGED
    assert verdict.files_changed == 1
    assert verdict.summary() == f"stale — 1 file changed since commit {_sha(repo)[:7]}"


def test_deleted_and_untracked_files_are_stale(repo: Path) -> None:
    baseline = (_sha(repo), _hashes(repo, "a.txt"))
    (repo / "a.txt").unlink()
    (repo / "new.md").write_text("never indexed")
    verdict = _evaluate(repo, baseline)
    assert verdict.status == freshness.STALE
    assert verdict.files_changed == 2
    assert "2 files changed" in verdict.summary()


def test_dirty_content_the_index_already_holds_stays_fresh(repo: Path) -> None:
    """Indexing a dirty tree is normal — git sees a diff, the index does not."""
    (repo / "a.txt").write_text("indexed while dirty")
    verdict = _evaluate(repo, (_sha(repo), _hashes(repo, "a.txt")))
    assert verdict.status == freshness.FRESH


def test_commits_ahead_report_commits_behind(repo: Path) -> None:
    baseline = (_sha(repo), _hashes(repo, "a.txt"))
    (repo / "a.txt").write_text("c2")
    run_git(repo, "commit", "-am", "c2")
    verdict = _evaluate(repo, baseline)
    assert verdict.status == freshness.STALE
    assert verdict.commits_behind == 1
    assert verdict.files_changed == 1
    assert "(1 commit behind HEAD)" in verdict.summary()


def test_commits_outside_the_source_path_stay_fresh(repo: Path) -> None:
    source = repo / "docs"
    source.mkdir()
    (source / "d.md").write_text("d")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "docs")
    baseline = (_sha(repo), {"d.md": xxhash.xxh64(b"d").hexdigest()})
    (repo / "elsewhere.txt").write_text("unrelated")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "elsewhere")
    verdict = _evaluate(source, baseline)
    assert verdict.status == freshness.FRESH
    assert verdict.commits_behind == 1


def test_detached_head_is_reported_not_hidden(repo: Path) -> None:
    run_git(repo, "checkout", "--detach")
    verdict = _evaluate(repo, (_sha(repo), _hashes(repo, "a.txt")))
    assert verdict.status == freshness.FRESH
    assert verdict.detached_head is True
    assert "detached HEAD at" in verdict.summary()


def test_rewritten_history_is_unknown(repo: Path) -> None:
    (repo / "b.txt").write_text("b")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "c2")
    gone = _sha(repo)
    run_git(repo, "reset", "--hard", "HEAD~1")
    (repo / "c.txt").write_text("c")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "rewritten")
    verdict = _evaluate(repo, (gone, {}))
    assert verdict.status == freshness.UNKNOWN
    assert verdict.reason == freshness.HISTORY_REWRITTEN
    assert verdict.summary() == (
        "unknown — the indexed commit is no longer an ancestor of HEAD "
        "(history was rewritten)"
    )


def test_missing_baseline_commit_is_unknown(repo: Path) -> None:
    verdict = _evaluate(repo, ("0" * 40, {}))
    assert verdict.status == freshness.UNKNOWN
    assert verdict.reason == freshness.HISTORY_MISSING


def test_no_baseline_is_unknown_not_fresh(repo: Path) -> None:
    verdict = _evaluate(repo, (None, None))
    assert verdict.status == freshness.UNKNOWN
    assert verdict.reason == freshness.NO_BASELINE
    assert verdict.head == _sha(repo)[:7]


def test_non_git_source_is_unknown(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    verdict = _evaluate(plain, ("deadbeef", {}))
    assert verdict.status == freshness.UNKNOWN
    assert verdict.reason == freshness.NO_REPO


def test_non_files_reader_is_unknown(repo: Path) -> None:
    verdict = _evaluate(repo, (_sha(repo), {}), reader_type="jira")
    assert verdict.status == freshness.UNKNOWN
    assert verdict.reason == freshness.NOT_FILES


def test_missing_source_path_is_unknown(repo: Path) -> None:
    verdict = _evaluate(repo / "gone", (_sha(repo), {}))
    assert verdict.status == freshness.UNKNOWN
    assert verdict.reason == freshness.NO_BASE_PATH


def test_read_baseline_tolerates_a_corrupt_state_file(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text("{not json")
    assert freshness.read_baseline(tmp_path) == (None, None)


def test_tracker_baseline_is_what_freshness_reads(tmp_path: Path, repo: Path) -> None:
    """The baseline's OWNER: ChangeTracker.build_state, persisted as state.json."""
    state = ChangeTracker(base_path=str(repo)).build_state([str(repo / "a.txt")])
    assert state.last_indexed_commit == _sha(repo)
    collection = tmp_path / "state"
    collection.mkdir()
    (collection / "state.json").write_text(state.to_json())

    commit, hashes = freshness.read_baseline(collection)
    assert commit == _sha(repo)
    assert hashes is not None and "a.txt" in hashes
    verdict = _evaluate(repo, (commit, hashes))
    assert verdict.status == freshness.FRESH


def test_facade_inspect_attaches_the_verdict(tmp_path: Path, repo: Path) -> None:
    base = tmp_path / "collections"
    collection = base / "docs"
    collection.mkdir(parents=True)
    collection.joinpath("manifest.json").write_text(
        json.dumps(
            {
                "reader": {"type": "localFiles", "basePath": str(repo)},
                "numberOfDocuments": 1,
                "numberOfChunks": 1,
            }
        )
    )
    state = ChangeTracker(base_path=str(repo)).build_state([str(repo / "a.txt")])
    collection.joinpath("state.json").write_text(state.to_json())

    from indexed.core.engine import inspect

    infos = inspect(["docs"], collections_path=str(base))
    assert infos[0].freshness is not None
    assert infos[0].freshness["status"] == freshness.FRESH
    assert infos[0].freshness["summary"] == (
        "fresh — the index matches the working tree"
    )


def test_indexed_file_hidden_by_gitignore_is_not_silently_fresh(repo: Path) -> None:
    """`git status` never reports an ignored file; the index still holds it."""
    (repo / ".gitignore").write_text("scratch.md\n")
    run_git(repo, "add", ".gitignore")
    run_git(repo, "commit", "-m", "ignore scratch")
    (repo / "scratch.md").write_text("indexed content")
    baseline = (_sha(repo), _hashes(repo, "a.txt", "scratch.md"))
    (repo / "scratch.md").write_text("changed after indexing")

    verdict = _evaluate(repo, baseline)

    assert verdict.status == freshness.STALE
    assert verdict.files_changed == 1
