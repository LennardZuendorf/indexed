"""Characterization: full v2 files-source lifecycle behavior net (core-v2/3).

Mirrors ``tests/characterization/test_lifecycle_files.py`` STYLE (real CLI via
``CliRunner``, real embedding model, KNOWN-HIT search assertions) but for the v2
engine, and adds the legs the v2 system test deliberately omits: an INCREMENTAL
update (new doc appears, unchanged docs are NOT re-embedded — proven by
docstore node-id + content-hash stability) and a DELETION (the removed doc
becomes unfindable). This is the R4/R5 net; it runs GREEN alongside v1's
untouched net.

The pure create/search/inspect/remove coverage overlaps
``tests/system/test_v2_create_search_lifecycle.py`` by design (this net is the
authoritative FULL v2 lifecycle — create→search→update→delete→inspect→remove);
the system test remains as the network-free (socket-guarded) create+search
proof.
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

COLLECTION = "files-net-v2"


def _create(collection: str, path: Path):
    return runner.invoke(
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


def _search(query: str, *, limit: int = 5) -> dict:
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
            COLLECTION,
            "--limit",
            str(limit),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _docstore(collections_dir: Path) -> dict:
    return json.loads(
        (collections_dir / COLLECTION / "storage" / "docstore.json").read_text()
    )


def _node_ids_for(docstore: dict, doc_id: str) -> set[str]:
    prefix = f"{doc_id}::"
    return {k for k in docstore["docstore/data"] if k.startswith(prefix)}


def _doc_hash(docstore: dict, doc_id: str) -> str | None:
    return (docstore.get("docstore/metadata", {}).get(doc_id) or {}).get("doc_hash")


def test_v2_files_lifecycle_create_search_update_delete_inspect_remove(
    local_workspace, files_corpus: Path
) -> None:
    ws = local_workspace

    # --- create (v2 engine) ----------------------------------------------
    created = _create(COLLECTION, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr

    manifest_path = ws.collections_dir / COLLECTION / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["version"] == "2"
    assert manifest["engine"]["vectorStore"] == "simple"
    assert manifest["engine"]["scoreKind"] == "cosine"
    assert "MiniLM" in manifest["engine"]["embedding"]["model"]

    # --- search: a KNOWN document is the top hit --------------------------
    payload = _search("penguin migration survey along the Antarctic coastline")
    assert payload["results"], "expected at least one search hit"
    assert payload["results"][0]["document_id"].endswith("needle.txt")
    assert "penguin" in payload["results"][0]["text"].lower()

    # A different query ranks a different document first (known-hit).
    other = _search("vector indexing embeddings retrieval")
    assert other["results"][0]["document_id"].endswith("beta.txt")

    # Snapshot the unchanged docs' node ids + content hashes before the update.
    ds_before = _docstore(ws.collections_dir)
    needle_ids_before = _node_ids_for(ds_before, "needle.txt")
    beta_ids_before = _node_ids_for(ds_before, "beta.txt")
    needle_hash_before = _doc_hash(ds_before, "needle.txt")
    assert needle_ids_before and beta_ids_before

    # --- update: add a new doc AND delete an existing one -----------------
    (files_corpus / "gamma.txt").write_text(
        "The volcanic soil analysis revealed unusual sulfur concentrations "
        "near the caldera rim.\n"
    )
    (files_corpus / "alpha.txt").unlink()  # deletion → must become unfindable

    updated = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "update", COLLECTION]
    )
    assert updated.exit_code == 0, updated.stdout + updated.stderr

    # New doc is searchable.
    post = _search("volcanic soil sulfur concentrations caldera")
    assert any(r["document_id"].endswith("gamma.txt") for r in post["results"]), (
        "newly indexed document should be searchable after update"
    )

    # Deleted doc is unfindable (never returned for its own distinctive phrase).
    alpha_hit = _search("semantic search finds documents by meaning keywords")
    assert not any(
        r["document_id"].endswith("alpha.txt") for r in alpha_hit["results"]
    ), "deleted document must not be findable after update"

    # INCREMENTAL proof: the unchanged docs kept their exact node ids AND their
    # content hash (they were skipped, not re-embedded); the deleted doc's nodes
    # are gone; the new doc's nodes are present.
    ds_after = _docstore(ws.collections_dir)
    assert _node_ids_for(ds_after, "needle.txt") == needle_ids_before
    assert _node_ids_for(ds_after, "beta.txt") == beta_ids_before
    assert _doc_hash(ds_after, "needle.txt") == needle_hash_before
    assert _node_ids_for(ds_after, "alpha.txt") == set()
    assert _node_ids_for(ds_after, "gamma.txt"), "new doc's nodes must be present"

    # --- inspect: engine-aware diagnostics show v2 + model + store --------
    inspected = runner.invoke(
        app,
        ["--local", "--simple-output", "--log-level", "ERROR", "inspect", COLLECTION],
    )
    assert inspected.exit_code == 0, inspected.stdout + inspected.stderr
    info = json.loads(inspected.stdout)
    assert info["engine"] == "2"
    assert info["vector_store"] == "simple"
    assert "MiniLM" in (info["embedding_model"] or "")

    # --- remove ----------------------------------------------------------
    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", COLLECTION, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr
    assert not (ws.collections_dir / COLLECTION).exists()
