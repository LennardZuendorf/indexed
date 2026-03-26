"""Performance benchmarks for search hot paths.

Tests the performance-critical paths that were optimized:
- CLI search command startup (lazy imports, no model load for --help)
- DocumentCollectionSearcher with cached mapping + orjson
- FAISS index save/load via native format (mmap) vs legacy pickle
- Embedding batch size impact
"""

import json
import os

import numpy as np
import pytest
from typer.testing import CliRunner
from unittest.mock import MagicMock

from indexed.app import app


# ---------------------------------------------------------------------------
# CLI command benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(min_rounds=3, max_time=1.0)
def test_cli_search_help(benchmark):
    """Benchmark: `indexed search --help` startup time.

    This measures the cost of importing the search command module and
    rendering help — WITHOUT loading any ML models. Should be <500ms.
    """
    runner = CliRunner()

    def run_search_help():
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        stdout = result.stdout.lower()
        assert "search" in stdout
        assert "query" in stdout

    benchmark(run_search_help)


@pytest.mark.benchmark(min_rounds=3, max_time=1.0)
def test_cli_index_search_help(benchmark):
    """Benchmark: `indexed index search --help` startup time.

    Tests the public (non-hidden) search command path.
    """
    runner = CliRunner()

    def run_index_search_help():
        result = runner.invoke(app, ["index", "search", "--help"])
        assert result.exit_code == 0
        stdout = result.stdout.lower()
        assert "search" in stdout
        assert "query" in stdout

    benchmark(run_index_search_help)


# ---------------------------------------------------------------------------
# Searcher hot-path benchmarks
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mock_collection(tmp_path_factory):
    """Create a realistic mock collection on disk for search benchmarks."""
    base = tmp_path_factory.mktemp("collections")
    collection_name = "bench-collection"
    indexer_name = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"
    coll_dir = base / collection_name

    # Create directory structure
    indexes_dir = coll_dir / "indexes" / indexer_name
    docs_dir = coll_dir / "documents"
    indexes_dir.mkdir(parents=True)
    docs_dir.mkdir(parents=True)

    num_docs = 100
    chunks_per_doc = 5
    total_chunks = num_docs * chunks_per_doc

    # Build index-document mapping
    mapping = {}
    for doc_idx in range(num_docs):
        doc_id = f"doc-{doc_idx:04d}"
        for chunk_idx in range(chunks_per_doc):
            global_idx = doc_idx * chunks_per_doc + chunk_idx
            mapping[str(global_idx)] = {
                "documentId": doc_id,
                "documentUrl": f"https://example.com/{doc_id}",
                "documentPath": f"{collection_name}/documents/{doc_id}.json",
                "chunkNumber": chunk_idx,
            }

    # Write mapping
    mapping_path = coll_dir / "indexes" / "index_document_mapping.json"
    mapping_path.write_text(json.dumps(mapping))

    # Write document files
    for doc_idx in range(num_docs):
        doc_id = f"doc-{doc_idx:04d}"
        doc = {
            "id": doc_id,
            "url": f"https://example.com/{doc_id}",
            "text": f"Full text of document {doc_idx}. " * 20,
            "chunks": [
                {
                    "indexedData": f"Chunk {ci} of document {doc_idx}. " * 10,
                    "chunkNumber": ci,
                }
                for ci in range(chunks_per_doc)
            ],
            "modifiedTime": "2025-01-01T00:00:00+00:00",
        }
        (docs_dir / f"{doc_id}.json").write_text(json.dumps(doc))

    # Create FAISS index with random vectors
    import faiss

    dimension = 384  # all-MiniLM-L6-v2
    inner_index = faiss.IndexFlatL2(dimension)
    index = faiss.IndexIDMap(inner_index)
    vectors = np.random.rand(total_chunks, dimension).astype(np.float32)
    ids = np.arange(total_chunks, dtype=np.int64)
    index.add_with_ids(vectors, ids)

    # Save in native FAISS format
    faiss.write_index(index, str(indexes_dir / "indexer.faiss"))

    # Also save in legacy pickle format for comparison
    import pickle

    with open(str(indexes_dir / "indexer"), "wb") as f:
        pickle.dump(faiss.serialize_index(index), f)

    # Write manifest
    manifest = {
        "collectionName": collection_name,
        "updatedTime": "2025-01-01T00:00:00+00:00",
        "lastModifiedDocumentTime": "2025-01-01T00:00:00+00:00",
        "numberOfDocuments": num_docs,
        "numberOfChunks": total_chunks,
        "indexers": [{"name": indexer_name}],
    }
    (coll_dir / "manifest.json").write_text(json.dumps(manifest))

    return {
        "base_path": str(base),
        "collection_name": collection_name,
        "indexer_name": indexer_name,
        "num_docs": num_docs,
        "total_chunks": total_chunks,
        "dimension": dimension,
    }


@pytest.mark.benchmark(min_rounds=3, max_time=2.0)
def test_searcher_cached_mapping(benchmark, mock_collection):
    """Benchmark: DocumentCollectionSearcher with cached mapping.

    Measures search latency when mapping is already cached (MCP warm path).
    The mapping + document caches eliminate repeated JSON I/O.
    """
    from core.v1.engine.core.documents_collection_searcher import (
        DocumentCollectionSearcher,
    )
    from core.v1.engine.persisters.disk_persister import DiskPersister

    persister = DiskPersister(base_path=mock_collection["base_path"])

    # Create a mock indexer that returns fake FAISS results
    mock_indexer = MagicMock()
    mock_indexer.get_name.return_value = mock_collection["indexer_name"]

    # Simulate FAISS returning top 10 results
    scores = np.array(
        [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]], dtype=np.float32
    )
    indexes = np.array([[0, 5, 10, 15, 20, 25, 30, 35, 40, 45]], dtype=np.int64)
    mock_indexer.search.return_value = (scores, indexes)

    searcher = DocumentCollectionSearcher(
        collection_name=mock_collection["collection_name"],
        indexer=mock_indexer,
        persister=persister,
    )

    # Warm up the caches (first call loads mapping + documents)
    searcher.search(
        "warm up query", max_number_of_chunks=10, include_matched_chunks_content=True
    )

    def run_search():
        result = searcher.search(
            "benchmark query",
            max_number_of_chunks=10,
            max_number_of_documents=5,
            include_matched_chunks_content=True,
        )
        assert len(result["results"]) > 0

    benchmark(run_search)


@pytest.mark.benchmark(min_rounds=3, max_time=2.0)
def test_searcher_first_search(benchmark, mock_collection):
    """Benchmark: DocumentCollectionSearcher first search (cold mapping).

    Measures search latency when mapping needs to be loaded from disk.
    This is the CLI path — one search per process.
    """
    from core.v1.engine.core.documents_collection_searcher import (
        DocumentCollectionSearcher,
    )
    from core.v1.engine.persisters.disk_persister import DiskPersister

    persister = DiskPersister(base_path=mock_collection["base_path"])

    mock_indexer = MagicMock()
    mock_indexer.get_name.return_value = mock_collection["indexer_name"]
    scores = np.array([[0.1, 0.2, 0.3, 0.4, 0.5]], dtype=np.float32)
    indexes = np.array([[0, 10, 20, 30, 40]], dtype=np.int64)
    mock_indexer.search.return_value = (scores, indexes)

    def run_cold_search():
        # Create a fresh searcher each time (simulates CLI cold start)
        searcher = DocumentCollectionSearcher(
            collection_name=mock_collection["collection_name"],
            indexer=mock_indexer,
            persister=persister,
        )
        result = searcher.search(
            "cold query",
            max_number_of_chunks=5,
            max_number_of_documents=3,
            include_matched_chunks_content=True,
        )
        assert len(result["results"]) > 0

    benchmark(run_cold_search)


# ---------------------------------------------------------------------------
# FAISS index I/O benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(min_rounds=3, max_time=2.0)
def test_faiss_load_native_mmap(benchmark, mock_collection):
    """Benchmark: FAISS index load via native read_index with mmap.

    This is the new optimized path using faiss.read_index + IO_FLAG_MMAP.
    """
    import faiss

    index_path = os.path.join(
        mock_collection["base_path"],
        mock_collection["collection_name"],
        "indexes",
        mock_collection["indexer_name"],
        "indexer.faiss",
    )

    def load_native():
        idx = faiss.read_index(index_path, faiss.IO_FLAG_MMAP)
        assert idx.ntotal == mock_collection["total_chunks"]

    benchmark(load_native)


@pytest.mark.benchmark(min_rounds=3, max_time=2.0)
def test_faiss_load_legacy_pickle(benchmark, mock_collection):
    """Benchmark: FAISS index load via legacy pickle + deserialize.

    This is the old path: pickle.load() -> faiss.deserialize_index().
    """
    import faiss
    import pickle

    index_path = os.path.join(
        mock_collection["base_path"],
        mock_collection["collection_name"],
        "indexes",
        mock_collection["indexer_name"],
        "indexer",
    )

    def load_pickle():
        with open(index_path, "rb") as f:
            serialized = pickle.load(f)
        idx = faiss.deserialize_index(serialized)
        assert idx.ntotal == mock_collection["total_chunks"]

    benchmark(load_pickle)


# ---------------------------------------------------------------------------
# JSON serialization benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(min_rounds=5, max_time=2.0)
def test_orjson_loads_mapping(benchmark, mock_collection):
    """Benchmark: orjson.loads on the index-document mapping file.

    Measures JSON parse speed for a realistic mapping file (500 entries).
    """
    try:
        import orjson
    except ImportError:
        pytest.skip("orjson not installed")

    mapping_path = os.path.join(
        mock_collection["base_path"],
        mock_collection["collection_name"],
        "indexes",
        "index_document_mapping.json",
    )

    with open(mapping_path, "rb") as f:
        raw_bytes = f.read()

    def parse_orjson():
        result = orjson.loads(raw_bytes)
        assert len(result) == mock_collection["total_chunks"]

    benchmark(parse_orjson)


@pytest.mark.benchmark(min_rounds=5, max_time=2.0)
def test_stdlib_json_loads_mapping(benchmark, mock_collection):
    """Benchmark: stdlib json.loads on the index-document mapping file.

    Comparison baseline against orjson for the same data.
    """
    mapping_path = os.path.join(
        mock_collection["base_path"],
        mock_collection["collection_name"],
        "indexes",
        "index_document_mapping.json",
    )

    with open(mapping_path, "r") as f:
        raw_text = f.read()

    def parse_json():
        result = json.loads(raw_text)
        assert len(result) == mock_collection["total_chunks"]

    benchmark(parse_json)
