"""Store-dispatch INTEGRATION probe (R9, core-v2/2d).

``test_stores.py`` unit-tests ``load_storage_context`` fail-loud against a
hand-built manifest and an EMPTY persist dir (2b). This is the integration-
level companion the plan.md core-v2/2 scenario asks for: "probe with a fake
second store id -> clear error, not silent FAISS/simple fallback". It builds a
REAL v2 collection end to end (ingestion + adapter + VectorStoreIndex +
persist, MockEmbedding — no real model needed), hand-edits the on-disk
manifest's ``engine.vectorStore`` to an unsupported id, and proves the
recorded (still fully loadable) ``simple`` data on disk is never silently
read despite the identity mismatch — the dispatch check must fire BEFORE any
storage I/O, at both the store layer directly and through the full v2
search path.
"""

from __future__ import annotations

import json
from pathlib import Path

from indexed.core.errors import UnknownVectorStoreError
from indexed.core.v2 import ingestion, retrieval
from indexed.core.v2.manifest import V2Manifest
from indexed.protocols import SourceConfig

from tests.unit.indexed.core.v2._engine_helpers import (
    make_connector_factory,
    make_doc,
    mock_embedding,
)


def _cfg(name: str) -> SourceConfig:
    return SourceConfig(name=name, type="localFiles", base_url_or_path="")


def _build_real_v2_collection(cols: Path, name: str) -> Path:
    """A real, on-disk v2 collection (real SimpleVectorStore persist, no model)."""
    with mock_embedding(embed_dim=8):
        ingestion.create(
            [SourceConfig(name=name, type="localFiles", base_url_or_path="/corpus")],
            use_cache=False,
            connector_factory=make_connector_factory(
                [make_doc("d1", ["penguin migration"])]
            ),
            collections_path=str(cols),
        )
    return cols / name


def _corrupt_recorded_store(collection_dir: Path, *, fake_store: str) -> None:
    """Hand-edit the manifest's ``engine.vectorStore`` — the on-disk SimpleVectorStore
    JSON under ``storage/`` is left untouched (still real, still loadable) so a
    silent-fallback bug would actually succeed and mask the regression."""
    manifest_path = collection_dir / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["engine"]["vectorStore"] = fake_store
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")


def test_load_storage_context_rejects_real_collection_with_altered_store_id(
    tmp_path: Path,
) -> None:
    """The store layer, called on a REAL persisted collection whose manifest was
    altered to record an unsupported store, still fails loud — proving the
    dispatch check runs before any I/O against the (perfectly readable) simple
    store files already on disk."""
    from indexed.core.v2.stores import load_storage_context

    cols = tmp_path / "cols"
    collection_dir = _build_real_v2_collection(cols, "c1")
    _corrupt_recorded_store(collection_dir, fake_store="qdrant")

    raw = json.loads((collection_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest = V2Manifest.from_disk(raw)

    try:
        load_storage_context(collection_dir / "storage", manifest)
        raised = False
    except UnknownVectorStoreError as exc:
        raised = True
        message = str(exc)
        assert "qdrant" in message
        assert "simple" in message
    assert raised, "expected UnknownVectorStoreError, got a silent load"

    # The real simple-store files are untouched and still fully loadable under
    # their true identity — proving nothing was corrupted, only mis-recorded.
    from llama_index.core import StorageContext

    sc = StorageContext.from_defaults(persist_dir=str(collection_dir / "storage"))
    assert type(sc.vector_store).__name__ == "SimpleVectorStore"


def test_search_on_altered_store_id_surfaces_named_error_not_fake_hits(
    tmp_path: Path,
) -> None:
    """End to end through ``retrieval.search`` (per-collection failures are
    captured, never raised — matching v1): the altered collection returns an
    error entry naming both the recorded and supported stores, NEVER silently
    substituted results from the (still-present, still-loadable) simple data."""
    cols = tmp_path / "cols"
    collection_dir = _build_real_v2_collection(cols, "c1")
    _corrupt_recorded_store(collection_dir, fake_store="qdrant")

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin", configs=[_cfg("c1")], collections_path=str(cols)
        )

    assert "error" in res["c1"], res["c1"]
    assert "results" not in res["c1"]
    assert "qdrant" in res["c1"]["error"]
    assert "simple" in res["c1"]["error"]


def test_search_on_healthy_collection_unaffected_by_the_guard(tmp_path: Path) -> None:
    """Control: a collection recording its TRUE store id (``simple``) searches
    normally — the guard only fires on a genuine mismatch."""
    cols = tmp_path / "cols"
    _build_real_v2_collection(cols, "c1")

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin", configs=[_cfg("c1")], collections_path=str(cols)
        )

    assert "error" not in res["c1"], res["c1"]
    assert res["c1"]["results"]
