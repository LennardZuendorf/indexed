"""Tests for search service."""
from unittest.mock import Mock, patch

from core.v1.engine.services.search_service import SearchService, search
from core.v1.engine.services.models import SourceConfig


class TestSearchService:
    """Test SearchService class."""

    def test_init(self):
        """Test initialization."""
        service = SearchService()

        assert service._persister is not None
        assert service._searcher_cache == {}

    @patch("core.v1.engine.services.search_service.create_collection_searcher")
    def test_get_searcher_creates_new(self, mock_factory):
        """Test _get_searcher creates new searcher when not cached."""
        mock_searcher = Mock()
        mock_factory.return_value = mock_searcher

        service = SearchService()

        searcher = service._get_searcher(
            collection_name="test-collection", index_name="test-indexer"
        )

        assert searcher == mock_searcher
        mock_factory.assert_called_once_with(
            collection_name="test-collection", index_name="test-indexer"
        )

    @patch("core.v1.engine.services.search_service.create_collection_searcher")
    def test_get_searcher_uses_cache(self, mock_factory):
        """Test _get_searcher uses cached searcher."""
        mock_searcher = Mock()
        mock_factory.return_value = mock_searcher

        service = SearchService()

        # First call creates
        searcher1 = service._get_searcher(
            collection_name="test-collection", index_name="test-indexer"
        )

        # Second call uses cache
        searcher2 = service._get_searcher(
            collection_name="test-collection", index_name="test-indexer"
        )

        assert searcher1 == searcher2
        mock_factory.assert_called_once()  # Only called once
        assert len(service._searcher_cache) == 1  # One cached instance

    def test_discover_collections(self):
        """Test _discover_collections when collections exist."""
        service = SearchService()

        # Mock persister methods - read_folder_files returns file paths
        service._persister.read_folder_files = Mock(
            return_value=[
                "collection1/manifest.json",
                "collection1/data.json",
                "collection2/manifest.json",
                "collection2/data.json",
                "not-a-collection/data.json"
            ]
        )
        
        # Mock is_path_exists to return True for manifests
        def mock_is_path_exists(path):
            return path in ["collection1/manifest.json", "collection2/manifest.json"]
        
        service._persister.is_path_exists = Mock(side_effect=mock_is_path_exists)

        result = service._discover_collections()

        assert sorted(result) == ["collection1", "collection2"]

    def test_discover_collections_none_exist(self):
        """Test _discover_collections when no collections exist."""
        service = SearchService()
        service._persister.read_folder_files = Mock(return_value=[])

        result = service._discover_collections()

        assert result == []

    def test_get_default_indexer(self):
        """Test _get_default_indexer constructs correct name."""
        service = SearchService()

        # Read manifest content
        def mock_read_json(path):
            if path.endswith("manifest.json"):
                return {
                    "indexer": "FAISS_IndexFlatL2",
                    "embeddings": "all-MiniLM-L6-v2",
                }
            return {}

        service._persister.read_json = Mock(side_effect=mock_read_json)

        result = service._get_default_indexer("test-collection")

        assert result == "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"

    @patch("core.v1.engine.services.search_service.create_collection_searcher")
    def test_search_with_configs(self, mock_factory):
        """Test search with explicit configs."""
        mock_searcher = Mock()
        mock_searcher.search.return_value = {"hits": []}
        mock_factory.return_value = mock_searcher

        service = SearchService()
        configs = [
            SourceConfig(
                name="test-collection",
                type="localFiles",
                base_url_or_path="./docs",
                indexer="test-indexer",
            )
        ]

        result = service.search(
            query="test query",
            configs=configs,
            max_chunks=10,
            max_docs=5,
            include_full_text=True,
            include_all_chunks=True,
            include_matched_chunks=True,
        )

        assert "test-collection" in result
        assert result["test-collection"] == {"hits": []}

        # Verify searcher creation
        mock_factory.assert_called_once_with(
            collection_name="test-collection", index_name="test-indexer"
        )

        # Verify search parameters
        mock_searcher.search.assert_called_once_with(
            query="test query",
            max_number_of_chunks=10,
            max_number_of_documents=5,
            include_text_content=True,
            include_all_chunks_content=True,
            include_matched_chunks_content=True,
        )

    @patch("core.v1.engine.services.search_service.create_collection_searcher")
    def test_search_auto_discovery(self, mock_factory):
        """Test search with auto-discovery (configs=None)."""
        mock_searcher = Mock()
        mock_searcher.search.return_value = {"hits": []}
        mock_factory.return_value = mock_searcher

        service = SearchService()
        service._persister.read_folder_files = Mock(
            return_value=["collection1/manifest.json"]
        )
        service._persister.is_path_exists = Mock(return_value=True)
        service._persister.read_json = Mock(
            return_value={
                "indexer": "FAISS_IndexFlatL2",
                "embeddings": "all-MiniLM-L6-v2",
            }
        )

        result = service.search(
            query="test query",
            configs=None,  # Auto-discover
            max_chunks=10,
            max_docs=5,
            include_full_text=True,
            include_all_chunks=True,
            include_matched_chunks=True,
        )

        assert "collection1" in result
        assert result["collection1"] == {"hits": []}

        # Verify searcher creation with discovered collection
        mock_factory.assert_called_once_with(
            collection_name="collection1",
            index_name="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
        )

        # Verify search parameters
        mock_searcher.search.assert_called_once_with(
            query="test query",
            max_number_of_chunks=10,
            max_number_of_documents=5,
            include_text_content=True,
            include_all_chunks_content=True,
            include_matched_chunks_content=True,
        )

    @patch("core.v1.engine.services.search_service.create_collection_searcher")
    def test_search_error_handling(self, mock_factory):
        """Test search handles errors gracefully."""
        mock_searcher = Mock()
        mock_searcher.search.side_effect = Exception("Search failed")
        mock_factory.return_value = mock_searcher

        service = SearchService()
        configs = [
            SourceConfig(
                name="test-collection",
                type="localFiles",
                base_url_or_path="./docs",
                indexer="test-indexer",
            )
        ]

        result = service.search("test query", configs=configs)

        assert "test-collection" in result
        assert "error" in result["test-collection"]
        assert "Search failed" in result["test-collection"]["error"]


class TestSearchFunctionalInterface:
    """Test functional search interface."""

    @patch("core.v1.engine.services.search_service._default_service")
    def test_search_function_delegates_to_service(self, mock_service):
        """Test that search function delegates to default service."""
        mock_service.search.return_value = {"test": "result"}

        # Create test config
        config = SourceConfig(
            name="test-collection",
            type="localFiles",
            base_url_or_path="./docs",
            indexer="test-indexer",
        )

        # Call with all parameters
        result = search(
            query="test query",
            configs=[config],
            max_chunks=10,
            max_docs=5,
            score_threshold=1.5,
            include_full_text=True,
            include_all_chunks=True,
            include_matched_chunks=True,
        )

        assert result == {"test": "result"}
        mock_service.search.assert_called_once_with(
            query="test query",
            configs=[config],
            max_chunks=10,
            max_docs=5,
            score_threshold=1.5,
            include_full_text=True,
            include_all_chunks=True,
            include_matched_chunks=True,
            progress_callback=None,
        )

    @patch("core.v1.engine.services.search_service._default_service")
    def test_search_function_with_defaults(self, mock_service):
        """Test search function with default parameters."""
        mock_service.search.return_value = {}

        # Call with minimal parameters
        result = search("test query")

        assert result == {}
        mock_service.search.assert_called_once_with(
            query="test query",
            configs=None,
            max_chunks=None,
            max_docs=None,
            score_threshold=None,
            include_full_text=False,
            include_all_chunks=False,
            include_matched_chunks=False,
            progress_callback=None,
        )