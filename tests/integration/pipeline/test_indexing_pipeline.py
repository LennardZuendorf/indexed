"""Integration tests for the full indexing pipeline.

Tests end-to-end indexing from connector → reader → converter → embedding → storage.
"""

import pytest
from pathlib import Path
from core.v1.engine.services.collection_service import create
from core.v1.engine.services.models import SourceConfig
from core.v1.engine.indexes.indexer_registry import build_indexer_name

# Use a valid indexer name for tests
TEST_INDEXER = build_indexer_name("all-MiniLM-L6-v2")


@pytest.mark.integration
@pytest.mark.slow
def test_filesystem_indexing_pipeline(
    clean_config,
    sample_documents,
    temp_collections_path
):
    """Test complete indexing pipeline end-to-end with filesystem connector."""
    source_config = SourceConfig(
        name="test-collection",
        type="localFiles",
        base_url_or_path=str(sample_documents),
        indexer=TEST_INDEXER,
        reader_opts={
            "includePatterns": [r".*\.md$"],
            "excludePatterns": []
        }
    )
    
    # Execute pipeline
    create(
        [source_config],
        config_service=clean_config,
        collections_path=temp_collections_path
    )
    
    # Verify results
    index_path = Path(temp_collections_path) / "test-collection"
    assert index_path.exists(), "Collection directory should be created"
    
    # Check for expected files
    assert (index_path / "manifest.json").exists(), "Manifest file should exist"
    
    # Note: Actual index files depend on the IndexerFactory implementation
    # which may create different file structures


@pytest.mark.integration
@pytest.mark.slow
def test_multiple_document_indexing(
    clean_config,
    temp_workspace,
    temp_collections_path
):
    """Test indexing pipeline with multiple documents."""
    # Create test documents
    docs_dir = temp_workspace / "multi_docs"
    docs_dir.mkdir()
    
    for i in range(5):
        (docs_dir / f"doc{i}.md").write_text(
            f"# Document {i}\n\n"
            f"This is test document {i} with content about testing.\n"
            f"It includes information relevant to document {i}."
        )
    
    source_config = SourceConfig(
        name="multi-collection",
        type="localFiles",
        base_url_or_path=str(docs_dir),
        indexer=TEST_INDEXER,
        reader_opts={
            "includePatterns": [r".*\.md$"],
            "excludePatterns": []
        }
    )
    
    # Execute pipeline
    create(
        [source_config],
        config_service=clean_config,
        collections_path=temp_collections_path
    )
    
    # Verify collection was created
    index_path = Path(temp_collections_path) / "multi-collection"
    assert index_path.exists()
    assert (index_path / "manifest.json").exists()


@pytest.mark.integration
@pytest.mark.slow
def test_indexing_with_cache(
    clean_config,
    sample_documents,
    temp_collections_path,
    temp_caches_path
):
    """Test indexing pipeline with caching enabled."""
    source_config = SourceConfig(
        name="cached-collection",
        type="localFiles",
        base_url_or_path=str(sample_documents),
        indexer=TEST_INDEXER,
        reader_opts={
            "includePatterns": [r".*\.md$"],
            "excludePatterns": []
        }
    )
    
    # First indexing run with cache
    create(
        [source_config],
        config_service=clean_config,
        use_cache=True,
        collections_path=temp_collections_path,
        caches_path=temp_caches_path
    )
    
    # Verify collection was created
    index_path = Path(temp_collections_path) / "cached-collection"
    assert index_path.exists()


@pytest.mark.integration
@pytest.mark.slow
def test_indexing_with_force_recreate(
    clean_config,
    sample_documents,
    temp_collections_path
):
    """Test indexing pipeline with force flag to recreate existing collection."""
    source_config = SourceConfig(
        name="force-collection",
        type="localFiles",
        base_url_or_path=str(sample_documents),
        indexer=TEST_INDEXER,
        reader_opts={
            "includePatterns": [r".*\.md$"],
            "excludePatterns": []
        }
    )
    
    # First indexing run
    create(
        [source_config],
        config_service=clean_config,
        collections_path=temp_collections_path
    )
    
    index_path = Path(temp_collections_path) / "force-collection"
    assert index_path.exists()
    
    # Second indexing run with force=True
    create(
        [source_config],
        config_service=clean_config,
        force=True,
        collections_path=temp_collections_path
    )
    
    # Collection should still exist
    assert index_path.exists()


@pytest.mark.integration
@pytest.mark.slow
def test_indexing_empty_directory(
    clean_config,
    temp_workspace,
    temp_collections_path
):
    """Test indexing pipeline with empty directory.
    
    Expected behavior: Collections with no documents are NOT created.
    This test verifies that the system handles empty directories gracefully
    without creating empty collections.
    """
    empty_dir = temp_workspace / "empty"
    empty_dir.mkdir(exist_ok=True)
    
    source_config = SourceConfig(
        name="empty-collection",
        type="localFiles",
        base_url_or_path=str(empty_dir),
        indexer=TEST_INDEXER,
        reader_opts={
            "includePatterns": [r".*\.md$"],
            "excludePatterns": []
        }
    )
    
    # Execute pipeline with empty directory
    # This should complete without error but not create a collection
    create(
        [source_config],
        config_service=clean_config,
        collections_path=temp_collections_path
    )
    
    # Collection directory should NOT be created when there are no documents
    index_path = Path(temp_collections_path) / "empty-collection"
    assert not index_path.exists(), "Empty collections should not be created"

