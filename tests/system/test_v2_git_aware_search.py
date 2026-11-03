"""System test: opt-in query-time git awareness on a v2 files collection.

A two-commit temp git repo is indexed with the real engine; then
``--changed-since HEAD~1`` must return only the file the second commit touched,
and ``--git-provenance`` must name that commit's author.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indexed.cli.app import app
from tests.conftest import model_available, run_git

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

COLLECTION = "files-v2-git-aware"
QUERY = "walrus migration survey beta"


def _create_v2(path: Path, collection: str = COLLECTION) -> None:
    created = runner.invoke(
        app,
        [
            "--engine",
            "v2",
            "--local",
            "--log-level",
            "ERROR",
            "create",
            "files",
            "--collection",
            collection,
            "--path",
            str(path),
            "--local",
            "--no-cache",
        ],
    )
    assert created.exit_code == 0, created.stdout + created.stderr


def _search(query: str, collection: str, *extra: str) -> dict:
    result = runner.invoke(
        app,
        [
            "--local",
            "--simple-output",
            "--log-level",
            "ERROR",
            "search",
            query,
            "--collection",
            collection,
            *extra,
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


@pytest.fixture
def git_corpus(tmp_path: Path) -> Path:
    """Two commits: the second edits ``beta.txt`` only, as 'Second Author'."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init")
    (repo / "alpha.txt").write_text("alpha document about penguin colonies\n")
    (repo / "beta.txt").write_text("beta document about walrus haul-outs\n")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "initial corpus")
    (repo / "beta.txt").write_text(
        "beta document about walrus migration survey routes\n"
    )
    run_git(repo, "add", "beta.txt")
    run_git(
        repo,
        "commit",
        "--author=Second Author <second@test.com>",
        "-m",
        "second commit",
    )
    return repo


def test_changed_since_and_git_provenance(local_workspace, git_corpus: Path) -> None:
    _create_v2(git_corpus)

    # --- changed-since HEAD~1: only the second commit's file survives ------
    filtered = _search(QUERY, COLLECTION, "--changed-since", "HEAD~1")
    assert filtered["results"], "expected at least one hit"
    assert {row["document_id"] for row in filtered["results"]} == {"beta.txt"}

    # --- provenance: the second commit (and its author) is named ----------
    provenanced = _search(QUERY, COLLECTION, "--git-provenance")
    beta_rows = [r for r in provenanced["results"] if r["document_id"] == "beta.txt"]
    assert beta_rows, "expected a beta.txt hit"
    assert beta_rows[0]["git_author"] == "Second Author"
    assert len(beta_rows[0]["git_commit"]) == 40
    assert beta_rows[0]["git_committed_at"].startswith("20")

    # --- the Rich detail card carries the same commit ----------------------
    # The --simple-output invocations above set a process-global flag; clear it
    # so this call renders the card instead of JSON.
    from indexed.cli.utils.simple_output import reset_simple_output

    reset_simple_output()
    rich = runner.invoke(
        app,
        [
            "--local",
            "--log-level",
            "ERROR",
            "search",
            QUERY,
            "--collection",
            COLLECTION,
            "--git-provenance",
            "--limit",
            "1",
        ],
    )
    assert rich.exit_code == 0, rich.stdout + rich.stderr
    assert "Last commit" in rich.stdout
    assert "Second Author" in rich.stdout

    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", COLLECTION, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr


def test_bad_changed_since_ref_exits_nonzero(local_workspace, git_corpus: Path) -> None:
    _create_v2(git_corpus)

    bad = runner.invoke(
        app,
        [
            "--local",
            "--log-level",
            "ERROR",
            "search",
            QUERY,
            "--collection",
            COLLECTION,
            "--changed-since",
            "no-such-ref",
        ],
    )
    assert bad.exit_code == 1
    assert "not a valid git ref" in bad.stdout

    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", COLLECTION, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr


# ── line-level blame (#60) ─────────────────────────────────────────────────


LINE_COLLECTION = "files-v2-line-blame"
LINE_QUERY = "walrus section"


def _function_block(name: str, terms: str, lines: int = 20) -> str:
    """A function big enough to be its OWN chunk, under the token budget."""
    body = [f"def {name}():", f'    """{terms} section."""', "    total = 0"]
    body.extend(f"    value_{i} = {i} + total  # {terms}" for i in range(lines))
    body.append("    return total")
    return "\n".join(body) + "\n"


@pytest.fixture
def line_blame_corpus(tmp_path: Path) -> tuple[Path, str, str]:
    """One file, two chunks, two commits: c2 rewrites a line inside ``beta`` only.

    The module is deliberately two medium functions: the code chunker emits one
    chunk per function (neither exceeds the token budget), so the two chunks'
    line spans belong to different commits. Both functions carry the query term.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init")
    alpha = _function_block("alpha", "walrus")
    beta = _function_block("beta", "walrus")
    (repo / "module.py").write_text(
        '"""Synthetic module."""\n\n' + alpha + "\n\n" + beta + "\n"
    )
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "initial module", "--date=2026-01-01T00:00:00+00:00")
    first = run_git(repo, "rev-parse", "HEAD").stdout.strip()

    # Same line count, so the indexed spans stay valid: only the marker changes,
    # and only inside ``beta`` — ``alpha``'s span must keep its c1 provenance.
    (repo / "module.py").write_text(
        '"""Synthetic module."""\n\n'
        + alpha
        + "\n\n"
        + beta.replace(
            "value_3 = 3 + total  # walrus",
            "value_3 = 3 + total  # walrus EDITED",
        )
        + "\n"
    )
    run_git(repo, "add", "module.py")
    run_git(
        repo,
        "commit",
        "--author=Second Author <second@test.com>",
        "--date=2026-01-02T00:00:00+00:00",
        "-m",
        "edit beta line",
    )
    second = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, first, second


def test_line_blame_resolves_two_chunks_of_one_file_to_two_commits(
    local_workspace, line_blame_corpus: tuple[Path, str, str]
) -> None:
    repo, first, second = line_blame_corpus
    _create_v2(repo, LINE_COLLECTION)

    blamed = _search(LINE_QUERY, LINE_COLLECTION, "--git-line-blame")
    rows = [r for r in blamed["results"] if r["document_id"] == "module.py"]
    assert len(rows) >= 2, f"expected both chunks of module.py, got {rows}"

    by_commit = {
        row["git_line_commit"]: row for row in rows if "git_line_commit" in row
    }
    # Two chunks of ONE file, attributed to TWO different commits.
    assert set(by_commit) == {first, second}
    assert by_commit[second]["git_line_author"] == "Second Author"
    assert by_commit[first]["git_line_start"] < by_commit[second]["git_line_start"]
    # Line-level only: the document-level triple stays off unless asked for.
    assert all("git_commit" not in row for row in rows)

    # --- the Rich detail card names the lines' commit too -------------------
    from indexed.cli.utils.simple_output import reset_simple_output

    reset_simple_output()
    rich = runner.invoke(
        app,
        [
            "--local",
            "--log-level",
            "ERROR",
            "search",
            LINE_QUERY,
            "--collection",
            LINE_COLLECTION,
            "--git-line-blame",
        ],
    )
    assert rich.exit_code == 0, rich.stdout + rich.stderr
    assert "Lines commit" in rich.stdout
    # The card names the span it attributed, alongside the commit line.
    assert "lines " in rich.stdout

    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", LINE_COLLECTION, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr


# ── git-signal re-rank (#144) ──────────────────────────────────────────────

RERANK_COLLECTION = "files-v2-git-rerank"
RERANK_QUERY = "walrus migration survey beta"


@pytest.fixture
def rerank_corpus(tmp_path: Path) -> Path:
    """``archive.txt`` is the closer match but was committed in 2020.

    ``current.txt`` sits a measured ~0.06 cosine behind it and was committed just
    now — so embedding similarity ranks the stale file first, and recency (a
    0.10 default weight) is what flips it. Both files live in one directory, so
    the path prefix the connector puts in each chunk cancels out.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init")
    (repo / "archive.txt").write_text(f"{RERANK_QUERY} survey\n")
    (repo / "current.txt").write_text(f"{RERANK_QUERY}\n")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "initial corpus", "--date=2020-01-01T00:00:00+00:00")
    (repo / "current.txt").write_text(f"{RERANK_QUERY} notes\n")
    run_git(repo, "add", "current.txt")
    run_git(repo, "commit", "-m", "recent edit")
    return repo


def _doc_order(payload: dict) -> list[str]:
    """Document ids in first-admission order (chunks of one doc can repeat)."""
    return list(dict.fromkeys(row["document_id"] for row in payload["results"]))


def _best_scores(payload: dict) -> dict[str, float]:
    """Each document's BEST chunk score (its filename chunk also matches)."""
    best: dict[str, float] = {}
    for row in payload["results"]:
        doc = row["document_id"]
        best[doc] = max(best.get(doc, 0.0), row["relevance_score"])
    return best


def test_git_rerank_lets_the_recent_file_beat_the_closer_stale_one(
    local_workspace, rerank_corpus: Path
) -> None:
    _create_v2(rerank_corpus, RERANK_COLLECTION)

    # --- default: cosine only, the closer (stale) file wins ---------------
    baseline = _search(RERANK_QUERY, RERANK_COLLECTION)
    assert _doc_order(baseline)[:2] == ["archive.txt", "current.txt"]
    assert {row["score_kind"] for row in baseline["results"]} == {"cosine"}
    baseline_best = _best_scores(baseline)
    assert baseline_best["archive.txt"] > baseline_best["current.txt"]

    # --- opt-in: git recency overtakes the cosine lead --------------------
    ranked = _search(RERANK_QUERY, RERANK_COLLECTION, "--git-rerank")
    assert _doc_order(ranked)[:2] == ["current.txt", "archive.txt"]
    assert {row["score_kind"] for row in ranked["results"]} == {"git-rerank"}

    best = _best_scores(ranked)
    assert best["current.txt"] > best["archive.txt"]
    # The boost is visible, not a silent reshuffle: the recent file's score
    # gains the recency bonus, the 2020 file's does not.
    assert best["current.txt"] - baseline_best["current.txt"] > 0.05
    assert abs(best["archive.txt"] - baseline_best["archive.txt"]) < 0.01

    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", RERANK_COLLECTION, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr
