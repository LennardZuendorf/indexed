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


def _inspect(collection: str) -> dict:
    result = runner.invoke(
        app,
        [
            "--local",
            "--simple-output",
            "--log-level",
            "ERROR",
            "inspect",
            collection,
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
    assert filtered["documents"], "expected at least one hit"
    assert {doc["id"] for doc in filtered["documents"]} == {"beta.txt"}

    # --- provenance: the second commit (and its author) is named ----------
    provenanced = _search(QUERY, COLLECTION, "--git-provenance")
    beta_docs = [d for d in provenanced["documents"] if d["id"] == "beta.txt"]
    assert beta_docs, "expected a beta.txt hit"
    beta_git = beta_docs[0]["git"]
    assert beta_git["author"] == "Second Author"
    assert len(beta_git["commit"]) == 40
    assert beta_git["committedAt"].startswith("20")

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


def test_storage_root_never_indexed(tmp_path: Path, monkeypatch) -> None:
    """``./.indexed`` created by ``--local`` is never source content.

    The scanned tree IS the workspace here, which is the shape that leaked:
    creating the collection materializes ``.indexed/`` (config, collections,
    ``.gitignore``) *before* the walk, so without the guard the collection
    indexed its own storage and ``--changed-since`` then listed
    ``.indexed/.gitignore`` as changed (it is untracked).
    """
    from indexed.config import reload as reload_config

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TQDM_DISABLE", "1")
    reload_config()

    run_git(tmp_path, "init")
    (tmp_path / "alpha.txt").write_text("alpha document about penguin colonies\n")
    (tmp_path / "beta.txt").write_text("beta document about walrus haul-outs\n")
    run_git(tmp_path, "add", "alpha.txt", "beta.txt")
    run_git(tmp_path, "commit", "-m", "initial corpus")
    (tmp_path / "beta.txt").write_text(
        "beta document about walrus migration survey routes\n"
    )
    run_git(tmp_path, "add", "beta.txt")
    run_git(tmp_path, "commit", "-m", "second commit")

    _create_v2(Path("."))

    # --- the collection holds the corpus, not its own storage --------------
    info = _inspect(COLLECTION)
    assert info["number_of_documents"] == 2

    searchable = {doc["id"] for doc in _search(QUERY, COLLECTION)["documents"]}
    assert searchable == {"alpha.txt", "beta.txt"}
    assert not any(doc_id.startswith(".indexed/") for doc_id in searchable)

    # --- changed-since does not report storage files -----------------------
    filtered = _search(QUERY, COLLECTION, "--changed-since", "HEAD~1")
    changed = {doc["id"] for doc in filtered["documents"]}
    assert changed == {"beta.txt"}
    assert not any(doc_id.startswith(".indexed/") for doc_id in changed)

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
    document = next(doc for doc in blamed["documents"] if doc["id"] == "module.py")
    hits = document["hits"]
    assert len(hits) >= 2
    by_commit = {hit["git"]["commit"]: hit["git"] for hit in hits if "git" in hit}
    assert set(by_commit) == {first, second}
    assert by_commit[second]["author"] == "Second Author"
    assert by_commit[first]["startLine"] < by_commit[second]["startLine"]
    assert "git" not in document

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
    return [doc["id"] for doc in payload["documents"]]


def _best_scores(payload: dict) -> dict[str, float]:
    return {
        doc["id"]: max(hit["score"] for hit in doc["hits"])
        for doc in payload["documents"]
    }


def test_git_rerank_lets_the_recent_file_beat_the_closer_stale_one(
    local_workspace, rerank_corpus: Path
) -> None:
    _create_v2(rerank_corpus, RERANK_COLLECTION)

    # --- default: cosine only, the closer (stale) file wins ---------------
    baseline = _search(RERANK_QUERY, RERANK_COLLECTION)
    assert _doc_order(baseline)[:2] == ["archive.txt", "current.txt"]
    assert {doc["score_kind"] for doc in baseline["documents"]} == {"cosine"}
    baseline_best = _best_scores(baseline)
    assert baseline_best["archive.txt"] > baseline_best["current.txt"]

    # --- opt-in: git recency overtakes the cosine lead --------------------
    ranked = _search(RERANK_QUERY, RERANK_COLLECTION, "--git-rerank")
    assert _doc_order(ranked)[:2] == ["current.txt", "archive.txt"]
    assert {doc["score_kind"] for doc in ranked["documents"]} == {"git-rerank"}

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
