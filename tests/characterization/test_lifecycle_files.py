"""Characterization: full files-source lifecycle behavior net (foundation/1).

Drives the real CLI end to end against a real temp corpus with real FAISS +
embeddings: ``create -> search -> update -> inspect -> remove``. The search
step asserts a *known* document is the top hit (not merely "no error"); the
update step asserts newly-added content becomes searchable; remove asserts the
collection is gone from disk.

This is a green characterization test: it pins current CORRECT behavior and
must stay green through every foundation refactor.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indexed.cli.app import app
from tests.conftest import model_available

runner = CliRunner()

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

COLLECTION = "files-net"


def _run(*args: str):
    """Invoke the CLI with a quiet, deterministic base flag set."""
    return runner.invoke(app, ["--simple-output", "--log-level", "ERROR", *args])


def _search(query: str, *, limit: int = 5) -> dict:
    result = _run("search", query, "--collection", COLLECTION, "--limit", str(limit))
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_files_lifecycle_create_search_update_inspect_remove(
    isolated_workspace, files_corpus: Path
) -> None:
    ws = isolated_workspace

    # --- create ----------------------------------------------------------
    created = runner.invoke(
        app,
        [
            "--log-level",
            "ERROR",
            "create",
            "files",
            "--collection",
            COLLECTION,
            "--path",
            str(files_corpus),
            "--no-cache",
        ],
    )
    assert created.exit_code == 0, created.stdout + created.stderr
    assert (ws.collections_dir / COLLECTION / "manifest.json").exists()

    # --- search: a KNOWN document is the top hit -------------------------
    payload = _search("penguin migration survey along the Antarctic coastline")
    assert payload["total_collections_searched"] >= 1
    assert payload["results"], "expected at least one search hit"
    top = payload["results"][0]
    assert top["document_id"].endswith("needle.txt"), (
        f"expected needle.txt as top hit, got {top['document_id']!r}"
    )
    assert "penguin" in top["text"].lower()

    # A query matching a different document ranks that document first.
    other = _search("vector indexing embeddings retrieval")
    assert other["results"][0]["document_id"].endswith("beta.txt")

    # --- update: new content becomes searchable --------------------------
    (files_corpus / "gamma.txt").write_text(
        "The volcanic soil analysis revealed unusual sulfur concentrations "
        "near the caldera rim.\n"
    )
    updated = runner.invoke(
        app,
        ["--log-level", "ERROR", "update", COLLECTION],
    )
    assert updated.exit_code == 0, updated.stdout + updated.stderr

    post = _search("volcanic soil sulfur concentrations caldera")
    assert any(r["document_id"].endswith("gamma.txt") for r in post["results"]), (
        "newly indexed document should be searchable after update"
    )

    # --- inspect ---------------------------------------------------------
    inspected = runner.invoke(
        app,
        ["--log-level", "ERROR", "inspect", COLLECTION],
    )
    assert inspected.exit_code == 0, inspected.stdout + inspected.stderr
    assert COLLECTION in inspected.stdout

    # --- remove ----------------------------------------------------------
    removed = runner.invoke(
        app,
        ["--log-level", "ERROR", "remove", COLLECTION, "--force"],
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr
    assert not (ws.collections_dir / COLLECTION).exists()
