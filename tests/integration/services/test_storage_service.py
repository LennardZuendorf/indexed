"""Integration tests for StorageService.

Tests FAISS storage service with persistence, search, and vector operations.
"""

import pytest
import numpy as np
from core.v1.engine.service.storage import StorageService


@pytest.mark.integration
def test_storage_service_basic_operations(temp_workspace):
    """Test basic StorageService operations."""
    storage_path = temp_workspace / "test_index.faiss"

    storage = StorageService(dimension=384, persistence_path=storage_path)

    # Add vectors
    vectors = np.random.rand(10, 384).astype("float32")
    ids = [f"doc-{i}" for i in range(10)]

    storage.add_vectors(vectors, ids)

    # Verify vectors were added
    assert storage.index.ntotal == 10


@pytest.mark.integration
def test_storage_service_persistence(temp_workspace):
    """Test FAISS storage persistence and reload."""
    storage_path = temp_workspace / "persistent_index.faiss"

    # Create and populate storage
    storage1 = StorageService(dimension=384, persistence_path=storage_path)

    vectors = np.random.rand(10, 384).astype("float32")
    ids = [f"chunk-{i:04d}" for i in range(10)]
    metadata = [{"doc_id": f"doc-{i//3}", "chunk_idx": i % 3} for i in range(10)]

    storage1.add_vectors(vectors, ids, metadata)

    # Save to disk
    storage1.save()

    assert storage_path.exists(), "Index file should be created"

    # Load in new instance
    storage2 = StorageService(dimension=384, persistence_path=storage_path)

    # Verify loaded correctly
    assert storage2.index.ntotal == 10
    assert len(storage2.id_mapping) == 10
    assert len(storage2.chunk_metadata) == 10


@pytest.mark.integration
def test_storage_service_search(temp_workspace):
    """Test FAISS storage search functionality."""
    storage_path = temp_workspace / "search_index.faiss"

    storage = StorageService(dimension=384, persistence_path=storage_path)

    # Add vectors with metadata
    np.random.seed(42)  # For reproducibility
    vectors = np.random.rand(20, 384).astype("float32")
    ids = [f"chunk-{i:04d}" for i in range(20)]
    metadata = [{"text": f"chunk {i}", "doc_id": f"doc-{i//5}"} for i in range(20)]

    storage.add_vectors(vectors, ids, metadata)

    # Create a query vector (similar to first vector)
    query_vector = vectors[0] + np.random.rand(384).astype("float32") * 0.1

    # Search
    results = storage.search(query_vector, top_k=5)

    assert len(results) > 0, "Should return search results"
    assert len(results) <= 5, "Should respect top_k limit"

    # Verify result structure
    for chunk_id, score, meta in results:
        assert isinstance(chunk_id, str)
        assert isinstance(score, (int, float))
        assert isinstance(meta, dict)


@pytest.mark.integration
def test_storage_service_with_metadata(temp_workspace):
    """Test StorageService metadata handling."""
    storage_path = temp_workspace / "metadata_index.faiss"

    storage = StorageService(dimension=384, persistence_path=storage_path)

    # Add vectors with rich metadata
    vectors = np.random.rand(5, 384).astype("float32")
    ids = [f"chunk-{i}" for i in range(5)]
    metadata = [
        {
            "document_id": f"doc-{i}",
            "chunk_index": i,
            "source": "test",
            "text": f"Sample text {i}",
        }
        for i in range(5)
    ]

    storage.add_vectors(vectors, ids, metadata)

    # Save and reload
    storage.save()

    storage2 = StorageService(dimension=384, persistence_path=storage_path)

    # Verify metadata persisted
    assert len(storage2.chunk_metadata) == 5

    for chunk_id in ids:
        assert chunk_id in storage2.chunk_metadata
        meta = storage2.chunk_metadata[chunk_id]
        assert "document_id" in meta
        assert "chunk_index" in meta
        assert "source" in meta


@pytest.mark.integration
def test_storage_service_incremental_adds(temp_workspace):
    """Test adding vectors incrementally."""
    storage_path = temp_workspace / "incremental_index.faiss"

    storage = StorageService(dimension=384, persistence_path=storage_path)

    # Add vectors in batches
    for batch in range(3):
        vectors = np.random.rand(5, 384).astype("float32")
        ids = [f"batch{batch}-chunk-{i}" for i in range(5)]

        storage.add_vectors(vectors, ids)

    # Should have 15 vectors total
    assert storage.index.ntotal == 15
    assert len(storage.id_mapping) == 15


@pytest.mark.integration
def test_storage_service_different_index_types(temp_workspace):
    """Test StorageService with different FAISS index types."""
    # Test with IndexFlatL2 (default)
    storage_l2 = StorageService(
        dimension=384,
        index_type="IndexFlatL2",
        persistence_path=temp_workspace / "l2_index.faiss",
    )

    vectors = np.random.rand(10, 384).astype("float32")
    ids = [f"doc-{i}" for i in range(10)]

    storage_l2.add_vectors(vectors, ids)
    assert storage_l2.index.ntotal == 10

    # Test with IndexFlatIP (inner product)
    storage_ip = StorageService(
        dimension=384,
        index_type="IndexFlatIP",
        persistence_path=temp_workspace / "ip_index.faiss",
    )

    storage_ip.add_vectors(vectors, ids)
    assert storage_ip.index.ntotal == 10


@pytest.mark.integration
def test_storage_service_empty_index(temp_workspace):
    """Test StorageService with no vectors."""
    storage_path = temp_workspace / "empty_index.faiss"

    storage = StorageService(dimension=384, persistence_path=storage_path)

    # Save empty index
    storage.save()

    assert storage_path.exists()

    # Load empty index
    storage2 = StorageService(dimension=384, persistence_path=storage_path)

    assert storage2.index.ntotal == 0
