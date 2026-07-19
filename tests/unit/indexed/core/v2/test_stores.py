"""Unit tests for core.v2 vector-store construction + LOAD dispatch (core-v2/2b).

Store construction and the ``simple`` round-trip exercise real LlamaIndex
``StorageContext``/``SimpleVectorStore`` (no model needed — these are plain
JSON stores). The fail-loud path proves an unknown recorded store raises
BEFORE any I/O, never silently falling back to ``simple`` (R9).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indexed.core.errors import UnknownVectorStoreError
from indexed.core.v2 import stores
from indexed.core.v2.manifest import V2Manifest
from indexed.protocols.models import ReaderDetails


def _manifest(vector_store: str = "simple") -> V2Manifest:
    return V2Manifest.new(
        collection_name="demo",
        reader=ReaderDetails(type="localFiles"),
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
        created_time="t",
        updated_time="t",
        last_modified_document_time="t",
        vector_store=vector_store,
    )


def test_known_vector_stores_is_simple_only() -> None:
    assert stores.known_vector_stores() == frozenset({"simple"})


def test_new_storage_context_builds_simple_stores() -> None:
    sc = stores.new_storage_context()
    assert type(sc.vector_store).__name__ == "SimpleVectorStore"
    assert type(sc.docstore).__name__ == "SimpleDocumentStore"
    assert type(sc.index_store).__name__ == "SimpleIndexStore"


def test_persist_then_load_simple_round_trips(tmp_path: Path) -> None:
    sc = stores.new_storage_context()
    storage_dir = tmp_path / "storage"
    stores.persist(sc, storage_dir)

    # tech.md "V2 on-disk layout": these three land under storage/.
    names = {p.name for p in storage_dir.iterdir()}
    assert {
        "docstore.json",
        "index_store.json",
        "default__vector_store.json",
    } <= names

    loaded = stores.load_storage_context(storage_dir, _manifest("simple"))
    assert type(loaded.vector_store).__name__ == "SimpleVectorStore"


def test_load_unknown_store_fails_loud_no_fallback(tmp_path: Path) -> None:
    # persist_dir is empty: the error must fire from the manifest dispatch,
    # before any load I/O — proving no silent simple/FAISS substitution.
    with pytest.raises(UnknownVectorStoreError) as excinfo:
        stores.load_storage_context(tmp_path, _manifest("qdrant"))

    message = str(excinfo.value)
    assert "qdrant" in message  # names the recorded store
    assert "simple" in message  # lists what this install supports
    assert excinfo.value.store == "qdrant"
    assert excinfo.value.known == ("simple",)


def test_unknown_vector_store_error_is_indexed_error() -> None:
    from indexed.config.errors import IndexedError
    from indexed.core.errors import CoreError

    err = UnknownVectorStoreError("qdrant", known=stores.known_vector_stores())
    assert isinstance(err, CoreError)
    assert isinstance(err, IndexedError)  # CLI exit codes / MCP envelopes work
