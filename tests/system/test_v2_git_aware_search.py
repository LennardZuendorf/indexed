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


def _create_v2(path: Path) -> None:
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
            COLLECTION,
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

    searchable = {row["document_id"] for row in _search(QUERY, COLLECTION)["results"]}
    assert searchable == {"alpha.txt", "beta.txt"}
    assert not any(doc_id.startswith(".indexed/") for doc_id in searchable)

    # --- changed-since does not report storage files -----------------------
    filtered = _search(QUERY, COLLECTION, "--changed-since", "HEAD~1")
    changed = {row["document_id"] for row in filtered["results"]}
    assert changed == {"beta.txt"}
    assert not any(doc_id.startswith(".indexed/") for doc_id in changed)

    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", COLLECTION, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr
