"""Unit tests for the ConvertedDocument -> TextNode adapter (core-v2/2a).

Proves the ref-doc linkage the adapter sets is exactly what a real LlamaIndex
docstore keys ``delete_ref_doc`` on — the API 2b/2c's ingestion/update path
depends on (see task report).
"""

from __future__ import annotations

from typing import Any

import pytest
from llama_index.core.schema import MetadataMode

pytestmark = pytest.mark.unit


def _doc(chunks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": "doc-1",
        "url": "file:///doc-1",
        "modifiedTime": "2026-01-01T00:00:00Z",
        "text": "full text",
        "chunks": (
            chunks
            if chunks is not None
            else [
                {"indexedData": "chunk zero"},
                {"indexedData": "chunk one", "metadata": {"heading": "H1"}},
            ]
        ),
    }


def test_to_nodes_ids_and_text() -> None:
    from indexed.core.v2.adapter import to_nodes

    nodes = to_nodes(_doc(), collection="demo")
    assert [n.id_ for n in nodes] == ["doc-1::chunk_0", "doc-1::chunk_1"]
    assert [n.text for n in nodes] == ["chunk zero", "chunk one"]


def test_to_nodes_ref_doc_id_matches_docstore_delete_key() -> None:
    """Round-trips through a real SimpleDocumentStore: proves the exact
    ref-doc linkage API (relationships[NodeRelationship.SOURCE]) that
    delete_ref_doc keys on — not just that `.ref_doc_id` reads back right.
    """
    from llama_index.core.storage.docstore import SimpleDocumentStore

    from indexed.core.v2.adapter import to_nodes

    nodes = to_nodes(_doc(), collection="demo")
    assert all(n.ref_doc_id == "doc-1" for n in nodes)

    store = SimpleDocumentStore()
    store.add_documents(nodes)
    assert sorted(store.docs.keys()) == ["doc-1::chunk_0", "doc-1::chunk_1"]

    store.delete_ref_doc("doc-1")
    assert store.docs == {}


def test_to_nodes_metadata_merges_chunk_metadata() -> None:
    from indexed.core.v2.adapter import to_nodes

    nodes = to_nodes(_doc(), collection="demo")
    assert nodes[0].metadata == {
        "source_id": "doc-1",
        "url": "file:///doc-1",
        "modified_time": "2026-01-01T00:00:00Z",
        "chunk_number": 0,
        "collection": "demo",
    }
    assert nodes[1].metadata == {
        "source_id": "doc-1",
        "url": "file:///doc-1",
        "modified_time": "2026-01-01T00:00:00Z",
        "chunk_number": 1,
        "collection": "demo",
        "heading": "H1",
    }


def test_to_nodes_empty_chunks_returns_empty_list() -> None:
    from indexed.core.v2.adapter import to_nodes

    assert to_nodes(_doc(chunks=[]), collection="demo") == []


def test_to_nodes_is_deterministic() -> None:
    from indexed.core.v2.adapter import to_nodes

    first = to_nodes(_doc(), collection="demo")
    second = to_nodes(_doc(), collection="demo")
    assert [n.id_ for n in first] == [n.id_ for n in second]
    assert [n.metadata for n in first] == [n.metadata for n in second]


def test_to_nodes_accepts_converted_document_model() -> None:
    from indexed.core.v2.adapter import to_nodes
    from indexed.protocols.models import ConvertedDocument

    doc = ConvertedDocument.model_validate(_doc())
    nodes = to_nodes(doc, collection="demo")
    assert [n.id_ for n in nodes] == ["doc-1::chunk_0", "doc-1::chunk_1"]


def _auth_doc() -> dict[str, Any]:
    return {
        "id": "auth.py",
        "url": "file:///tmp/some/very/long/path/auth.py",
        "modifiedTime": "2026-07-19T14:47:41",
        "chunks": [
            {"indexedData": "auth.py"},
            {"indexedData": "def login(): ...", "metadata": {"lang": "python"}},
        ],
    }


def test_embed_text_excludes_engine_metadata() -> None:
    from indexed.core.v2.adapter import to_nodes

    nodes = to_nodes(_auth_doc(), "demo")
    # The text sent to the embedder must be ONLY the chunk content (R8: 1:1 with v1).
    assert nodes[0].get_content(metadata_mode=MetadataMode.EMBED) == "auth.py"
    assert nodes[1].get_content(metadata_mode=MetadataMode.EMBED) == "def login(): ..."


def test_metadata_still_available_for_retrieval() -> None:
    from indexed.core.v2.adapter import to_nodes

    nodes = to_nodes(_auth_doc(), "demo")
    assert nodes[0].metadata["source_id"] == "auth.py"
    assert nodes[0].metadata["url"] == "file:///tmp/some/very/long/path/auth.py"
    assert nodes[0].metadata["collection"] == "demo"


def test_chunk_metadata_does_not_clobber_reserved_keys() -> None:
    # PR review #7: a chunk carrying a reserved key must not override the engine value.
    from indexed.core.v2.adapter import to_nodes

    doc = {
        "id": "d1",
        "url": "u1",
        "chunks": [
            {"indexedData": "x", "metadata": {"collection": "attacker", "lang": "py"}}
        ],
    }
    node = to_nodes(doc, "real-collection")[0]
    assert node.metadata["collection"] == "real-collection"  # engine value wins
    assert node.metadata["lang"] == "py"  # chunk's own extra metadata preserved
