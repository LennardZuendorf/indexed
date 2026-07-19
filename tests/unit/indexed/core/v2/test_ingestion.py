"""v2 CREATE path tests (core-v2/2c ``ingestion.create``).

Structural properties (manifest shape, node-count == chunk-count with NO
re-chunking, build-aside crash-safety, empty-corpus error) are MODEL-FREE via a
MockEmbedding. The KNOWN-HIT relevance test lives in the retrieval/facade
suites.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from indexed.core.v2 import ingestion
from indexed.protocols import SourceConfig

from tests.unit.indexed.core.v2._engine_helpers import (
    make_connector_factory,
    make_doc,
    mock_embedding,
)


def _cfg(name: str) -> SourceConfig:
    return SourceConfig(name=name, type="localFiles", base_url_or_path="/corpus")


def test_create_writes_version_marked_manifest_and_storage(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    docs = [
        make_doc("needle", ["penguin migration antarctic", "more penguin facts"]),
        make_doc("other", ["kubernetes autoscaler crash loop"]),
    ]
    with mock_embedding(embed_dim=8):
        ingestion.create(
            [_cfg("c1")],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )

    manifest = json.loads((cols / "c1" / "manifest.json").read_text())
    assert manifest["version"] == "2"
    assert manifest["collectionName"] == "c1"
    assert manifest["numberOfDocuments"] == 2
    assert manifest["numberOfChunks"] == 3  # 2 + 1 chunks
    assert manifest["reader"]["type"] == "localFiles"
    assert manifest["engine"]["embedding"]["dimension"] == 8
    assert manifest["engine"]["vectorStore"] == "simple"
    assert manifest["engine"]["scoreKind"] == "cosine"

    storage_files = {p.name for p in (cols / "c1" / "storage").iterdir()}
    assert {
        "docstore.json",
        "index_store.json",
        "default__vector_store.json",
    } <= storage_files


def test_node_count_equals_chunk_count_no_rechunk(tmp_path: Path) -> None:
    """The pre-chunked nodes must NOT be re-split by LlamaIndex: exactly one node
    per input chunk, with the deterministic ``<id>::chunk_<i>`` node ids."""
    cols = tmp_path / "cols"
    docs = [
        make_doc("d1", ["chunk a", "chunk b", "chunk c"]),
        make_doc("d2", ["only one"]),
    ]
    total_chunks = 3 + 1

    with mock_embedding(embed_dim=8):
        ingestion.create(
            [_cfg("c1")],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )

    docstore = json.loads((cols / "c1" / "storage" / "docstore.json").read_text())
    node_ids = set(docstore["docstore/data"].keys())
    assert len(node_ids) == total_chunks
    assert node_ids == {
        "d1::chunk_0",
        "d1::chunk_1",
        "d1::chunk_2",
        "d2::chunk_0",
    }
    manifest = json.loads((cols / "c1" / "manifest.json").read_text())
    assert manifest["numberOfChunks"] == total_chunks


def test_create_empty_corpus_raises_clear_error(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    with mock_embedding(embed_dim=8):
        with pytest.raises(ValueError, match="No documents found"):
            ingestion.create(
                [_cfg("empty")],
                use_cache=False,
                connector_factory=make_connector_factory([]),
                collections_path=str(cols),
            )
    assert not (cols / "empty").exists()


def test_build_aside_leaves_prior_collection_intact_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A create failure mid-build (persist raises) discards only the staging dir;
    the prior collection stays byte-identical and no ``.tmp-`` dir survives."""
    cols = tmp_path / "cols"
    docs = [make_doc("d1", ["penguin migration"])]

    with mock_embedding(embed_dim=8):
        ingestion.create(
            [_cfg("c1")],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )
    before = (cols / "c1" / "manifest.json").read_bytes()

    def boom_persist(storage_context, storage_dir):  # noqa: ANN001
        raise RuntimeError("persist boom")

    monkeypatch.setattr("indexed.core.v2.stores.persist", boom_persist)

    with mock_embedding(embed_dim=8):
        with pytest.raises(RuntimeError, match="persist boom"):
            ingestion.create(
                [_cfg("c1")],
                use_cache=False,
                connector_factory=make_connector_factory(docs),
                collections_path=str(cols),
            )

    # Prior collection untouched; no staging dir left behind.
    assert (cols / "c1" / "manifest.json").read_bytes() == before
    assert not any(p.name.startswith("c1.tmp-") for p in cols.iterdir())


def test_last_modified_document_time_is_max_across_docs(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    docs = [
        make_doc("a", ["x"], modified_time="2026-01-10T00:00:00+00:00"),
        make_doc("b", ["y"], modified_time="2026-03-01T00:00:00+00:00"),
    ]
    with mock_embedding(embed_dim=8):
        ingestion.create(
            [_cfg("c1")],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )
    manifest = json.loads((cols / "c1" / "manifest.json").read_text())
    assert manifest["lastModifiedDocumentTime"] == "2026-03-01T00:00:00+00:00"
