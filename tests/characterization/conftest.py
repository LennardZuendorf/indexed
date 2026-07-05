"""Shared fixtures for characterization smoke tests.

Exposes a single ``write_manifest`` helper for building a minimal on-disk
collection manifest. Tests that only need a manifest (e.g. MCP resource
smoke tests) use this; tests that need a searchable index build the
collection through the real engine instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DEFAULT_INDEXER_NAME = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"


@pytest.fixture
def write_manifest():
    """Return a helper that writes a ``manifest.json`` for a collection.

    The helper creates ``<collections_dir>/<collection_name>/manifest.json``
    with the standard on-disk schema and returns the collection directory.
    """

    def _write(
        collections_dir: Path,
        collection_name: str,
        *,
        number_of_documents: int = 1,
        number_of_chunks: int = 2,
        reader_type: str = "localFiles",
        indexer_name: str = DEFAULT_INDEXER_NAME,
    ) -> Path:
        coll_dir = collections_dir / collection_name
        coll_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "collectionName": collection_name,
            "updatedTime": "2025-01-01T00:00:00+00:00",
            "lastModifiedDocumentTime": "2025-01-01T00:00:00+00:00",
            "numberOfDocuments": number_of_documents,
            "numberOfChunks": number_of_chunks,
            "reader": {"type": reader_type},
            "indexers": [{"name": indexer_name}],
        }
        (coll_dir / "manifest.json").write_text(json.dumps(manifest))
        return coll_dir

    return _write
