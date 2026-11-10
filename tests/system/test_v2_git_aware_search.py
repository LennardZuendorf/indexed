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
