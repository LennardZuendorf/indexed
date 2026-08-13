"""System test: v2 engine CLI lifecycle — create/search/inspect/remove
(core-v2/2d, R4 surface parity).

Mirrors ``tests/characterization/test_lifecycle_files.py`` STYLE (real CLI via
``CliRunner``, real FAISS-free v2 collection, real embedding model, a KNOWN-HIT
search assertion) but for the v2 engine, and deliberately WITHOUT an update
step — v2 incremental update is core-v2/3's scope, which adds the FULL v2
lifecycle net (create->search->update->inspect->remove) alongside this one.
This file is scoped to create/search/inspect/remove so the two nets don't
duplicate coverage.
"""

from __future__ import annotations

import json
import socket
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

COLLECTION = "files-v2-net"


def _create_v2(collection: str, path: Path):
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


def _search(query: str, collection: str, *, limit: int = 5) -> dict:
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
            "--limit",
            str(limit),
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_v2_files_lifecycle_create_search_inspect_remove(
    local_workspace, files_corpus: Path
) -> None:
    ws = local_workspace

    # --- create (v2 engine, R1/R3) ----------------------------------------
    created = _create_v2(COLLECTION, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr

    manifest_path = ws.collections_dir / COLLECTION / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["version"] == "2"
    assert manifest["engine"]["vectorStore"] == "simple"
    assert manifest["engine"]["scoreKind"] == "cosine"
    assert "MiniLM" in manifest["engine"]["embedding"]["model"]

    # --- search: a KNOWN document is the top hit (R4, R11 cosine) ---------
    payload = _search(
        "penguin migration survey along the Antarctic coastline", COLLECTION
    )
    assert payload["results"], "expected at least one search hit"
    top = payload["results"][0]
    assert top["document_id"].endswith("needle.txt")
    assert "penguin" in top["text"].lower()

    # A different query ranks a different document first (known-hit, not just
    # "no error").
    other = _search("vector indexing embeddings retrieval", COLLECTION)
    assert other["results"][0]["document_id"].endswith("beta.txt")

    # --- inspect: engine-aware diagnostics show v2 + model + store (R13) --
    inspected = runner.invoke(
        app,
        [
            "--local",
            "--simple-output",
            "--log-level",
            "ERROR",
            "inspect",
            COLLECTION,
        ],
    )
    assert inspected.exit_code == 0, inspected.stdout + inspected.stderr
    info = json.loads(inspected.stdout)
    assert info["engine"] == "2"
    assert info["vector_store"] == "simple"
    assert info["embedding_provider"] == "local"
    assert "MiniLM" in (info["embedding_model"] or "")

    # Rich (non-simple-output) inspect surfaces an engine indicator too.
    inspected_rich = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "inspect", COLLECTION]
    )
    assert inspected_rich.exit_code == 0, inspected_rich.stdout + inspected_rich.stderr
    assert COLLECTION in inspected_rich.stdout
    assert "v2" in inspected_rich.stdout

    # --- remove -------------------------------------------------------------
    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", COLLECTION, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr
    assert not (ws.collections_dir / COLLECTION).exists()


def test_v2_default_create_and_search_never_touch_the_network(
    local_workspace, files_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8/R12 at the system level: a default v2 create+search (cached model)
    makes zero outbound network connections — the same socket-guard pattern
    core-v2/2b used for the embedding factory, applied here across the whole
    CLI create+search round trip."""
    collection = "files-v2-offline"

    class _NetworkAttempt(Exception):
        pass

    def _blocked_connect(self, address):  # noqa: ANN001
        raise _NetworkAttempt(f"network connect attempted: {address}")

    def _blocked_getaddrinfo(*args, **kwargs):  # noqa: ANN002, ANN003
        raise _NetworkAttempt(f"dns lookup attempted: {args}")

    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked_getaddrinfo)

    created = _create_v2(collection, files_corpus)
    assert created.exit_code == 0, created.stdout + created.stderr

    payload = _search("penguin migration antarctic coastline", collection)
    assert payload["results"]
    assert payload["results"][0]["document_id"].endswith("needle.txt")

    removed = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "remove", collection, "--force"]
    )
    assert removed.exit_code == 0, removed.stdout + removed.stderr
