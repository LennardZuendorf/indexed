"""Characterization: CLI search smoke test against an on-disk fixture collection."""

from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np
import pytest
from typer.testing import CliRunner

from indexed.app import app

runner = CliRunner()

COLLECTION_NAME = "smoke-collection"
INDEXER_NAME = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"


def _model_available() -> bool:
    try:
        from core.v1.engine.indexes.embeddings.model_manager import is_model_cached

        return is_model_cached("all-MiniLM-L6-v2")
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)


def _write_searchable_collection(collections_dir: Path, collection_name: str) -> None:
    coll_dir = collections_dir / collection_name
    indexes_dir = coll_dir / "indexes" / INDEXER_NAME
    docs_dir = coll_dir / "documents"
    indexes_dir.mkdir(parents=True)
    docs_dir.mkdir(parents=True)

    num_docs = 2
    chunks_per_doc = 2
    dimension = 384
    mapping: dict[str, dict[str, object]] = {}

    for doc_idx in range(num_docs):
        doc_id = f"doc-{doc_idx}"
        for chunk_idx in range(chunks_per_doc):
            global_idx = doc_idx * chunks_per_doc + chunk_idx
            mapping[str(global_idx)] = {
                "documentId": doc_id,
                "documentUrl": f"https://example.com/{doc_id}",
                "documentPath": f"{collection_name}/documents/{doc_id}.json",
                "chunkNumber": chunk_idx,
            }

    (coll_dir / "indexes" / "index_document_mapping.json").write_text(
        json.dumps(mapping)
    )

    for doc_idx in range(num_docs):
        doc_id = f"doc-{doc_idx}"
        doc = {
            "id": doc_id,
            "url": f"https://example.com/{doc_id}",
            "text": f"Smoke test document {doc_idx} about semantic search.",
            "chunks": [
                {
                    "indexedData": f"Chunk {ci} mentions semantic search indexing.",
                    "chunkNumber": ci,
                }
                for ci in range(chunks_per_doc)
            ],
            "modifiedTime": "2025-01-01T00:00:00+00:00",
        }
        (docs_dir / f"{doc_id}.json").write_text(json.dumps(doc))

    inner_index = faiss.IndexFlatL2(dimension)
    index = faiss.IndexIDMap(inner_index)
    vectors = np.random.rand(num_docs * chunks_per_doc, dimension).astype(np.float32)
    ids = np.arange(num_docs * chunks_per_doc, dtype=np.int64)
    index.add_with_ids(vectors, ids)
    faiss.write_index(index, str(indexes_dir / "indexer.faiss"))

    manifest = {
        "collectionName": collection_name,
        "updatedTime": "2025-01-01T00:00:00+00:00",
        "lastModifiedDocumentTime": "2025-01-01T00:00:00+00:00",
        "numberOfDocuments": num_docs,
        "numberOfChunks": num_docs * chunks_per_doc,
        "reader": {"type": "localFiles"},
        "indexers": [{"name": INDEXER_NAME}],
    }
    (coll_dir / "manifest.json").write_text(json.dumps(manifest))


@pytest.fixture
def smoke_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    from indexed_config import ensure_storage_dirs, get_local_root

    local_root = get_local_root(tmp_path)
    ensure_storage_dirs(local_root, is_local=True)
    collections_dir = local_root / "data" / "collections"
    _write_searchable_collection(collections_dir, COLLECTION_NAME)
    return tmp_path


def test_cli_search_smoke(smoke_workspace: Path) -> None:
    del smoke_workspace
    result = runner.invoke(
        app,
        [
            "--local",
            "--simple-output",
            "--log-level",
            "ERROR",
            "search",
            "semantic search",
            "--collection",
            COLLECTION_NAME,
            "--limit",
            "3",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["query"] == "semantic search"
    assert payload["total_collections_searched"] >= 1
    assert isinstance(payload["results"], list)
