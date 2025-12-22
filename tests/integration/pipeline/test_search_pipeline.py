"""Integration tests for the full search pipeline.

Tests end-to-end search from query → embedding → FAISS → results.
"""

import pytest
from pathlib import Path
from core.v1.engine.services.collection_service import create
from core.v1.engine.services.search_service import search
from core.v1.engine.services.models import SourceConfig
from core.v1.engine.indexes.indexer_registry import build_indexer_name

# Use a valid indexer name for tests
TEST_INDEXER = build_indexer_name("all-MiniLM-L6-v2")


@pytest.mark.integration
@pytest.mark.slow
def test_search_pipeline_basic(
    clean_config,
    sample_documents,
    temp_collections_path
):
    """Test complete search pipeline end-to-end."""
    # First, create the collection
    source_config = SourceConfig(
        name="search-test-collection",
        type="localFiles",
        base_url_or_path=str(sample_documents),
        indexer=TEST_INDEXER,
        reader_opts={
            "includePatterns": [r".*\.md$"],
            "excludePatterns": []
        }
    )
    
    create(
        [source_config],
        config_service=clean_config,
        collections_path=temp_collections_path
    )
    
    # Verify collection exists
    index_path = Path(temp_collections_path) / "search-test-collection"
    assert index_path.exists()
    
    # Now test search - create a minimal SourceConfig for searching
    search_config = SourceConfig(
        name="search-test-collection",
        type="localFiles",
        base_url_or_path="",  # Not used for search
        indexer=TEST_INDEXER
    )
    
    results = search(
        query="authentication methods",
        configs=[search_config],
        max_docs=5,
        collections_path=temp_collections_path
    )
    
    # Verify search results structure
    assert isinstance(results, dict)
    assert "results" in results or len(results) > 0


@pytest.mark.integration
@pytest.mark.slow
def test_search_multiple_queries(
    clean_config,
    sample_documents,
    temp_collections_path
):
    """Test search with multiple different queries."""
    # Create collection
    source_config = SourceConfig(
        name="multi-query-collection",
        type="localFiles",
        base_url_or_path=str(sample_documents),
        indexer=TEST_INDEXER,
        reader_opts={
            "includePatterns": [r".*\.md$"],
            "excludePatterns": []
        }
    )
    
    create(
        [source_config],
        config_service=clean_config,
        collections_path=temp_collections_path
    )
    
    # Test different queries
    queries = [
        "authentication methods",
        "API testing",
        "deployment strategies"
    ]
    
    search_config = SourceConfig(
        name="multi-query-collection",
        type="localFiles",
        base_url_or_path="",  # Not used for search
        indexer=TEST_INDEXER
    )
    
    for query in queries:
        results = search(
            query=query,
            configs=[search_config],
            max_docs=3,
            collections_path=temp_collections_path
        )
        
        # Each query should return results
        assert isinstance(results, dict)


@pytest.mark.integration
@pytest.mark.slow
def test_search_with_max_results(
    clean_config,
    temp_workspace,
    temp_collections_path
):
    """Test search with different max_docs limits."""
    # Create multiple test documents
    docs_dir = temp_workspace / "many_docs"
    docs_dir.mkdir()
    
    for i in range(10):
        (docs_dir / f"doc{i}.md").write_text(
            f"# Document {i}\n\n"
            f"Content about topic {i} and testing."
        )
    
    source_config = SourceConfig(
        name="max-results-collection",
        type="localFiles",
        base_url_or_path=str(docs_dir),
        indexer=TEST_INDEXER,
        reader_opts={
            "includePatterns": [r".*\.md$"],
            "excludePatterns": []
        }
    )
    
    create(
        [source_config],
        config_service=clean_config,
        collections_path=temp_collections_path
    )
    
    # Test with different limits
    search_config = SourceConfig(
        name="max-results-collection",
        type="localFiles",
        base_url_or_path="",  # Not used for search
        indexer=TEST_INDEXER
    )
    
    for max_docs in [1, 3, 5]:
        results = search(
            query="testing",
            configs=[search_config],
            max_docs=max_docs,
            collections_path=temp_collections_path
        )
        
        assert isinstance(results, dict)


@pytest.mark.integration
@pytest.mark.slow
def test_search_nonexistent_collection(temp_collections_path):
    """Test search with nonexistent collection."""
    # Attempt to search nonexistent collection
    # This should either raise an error or return empty results
    search_config = SourceConfig(
        name="nonexistent-collection",
        type="localFiles",
        base_url_or_path="",
        indexer=TEST_INDEXER
    )
    
    try:
        results = search(
            query="test query",
            configs=[search_config],
            max_docs=5,
            collections_path=temp_collections_path
        )
        # If no error, results should be empty or indicate no collection
        assert isinstance(results, dict)
    except (ValueError, FileNotFoundError, Exception) as e:
        # Expected to fail with collection not found
        assert "collection" in str(e).lower() or "not found" in str(e).lower()

