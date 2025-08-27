"""Tests for search_service."""

import json
from unittest.mock import Mock, patch

from main.services.search_service import SearchService, search
from main.services.models import SourceConfig


class TestSearchService:
    """Test SearchService class."""

    def test_init(self):
        """Test SearchService initialization."""
        service = SearchService()

        assert service._searcher_cache == {}
        assert service._persister is not None

    @patch("main.services.search_service.create_collection_searcher")
    def test_get_searcher_creates_new(self, mock_factory):
        """Test _get_searcher creates new searcher when not cached."""
        mock_searcher = Mock()
        mock_factory.return_value = mock_searcher

        service = SearchService()
        result = service._get_searcher("test-collection", "test-indexer")

        assert result == mock_searcher
        assert "test-collection:test-indexer" in service._searcher_cache
        mock_factory.assert_called_once_with(
            collection_name="test-collection", index_name="test-indexer"
        )

    @patch("main.services.search_service.create_collection_searcher")
    def test_get_searcher_uses_cache(self, mock_factory):
        """Test _get_searcher uses cached searcher."""
        mock_searcher = Mock()

        service = SearchService()
        # Pre-populate cache
        service._searcher_cache["test-collection:test-indexer"] = mock_searcher

        result = service._get_searcher("test-collection", "test-indexer")

        assert result == mock_searcher
        # Factory should not be called since we use cache
        mock_factory.assert_not_called()

    def test_discover_collections_success(self):
        """Test _discover_collections when collections exist."""
        service = SearchService()

        # Mock persister methods
        service._persister.read_folder_files = Mock(
            return_value=["collection1", "collection2", "not-a-collection"]
        )
        service._persister.is_path_exists = Mock(
            side_effect=lambda path: path
            in ["collection1/manifest.json", "collection2/manifest.json"]
        )

        result = service._discover_collections()

        assert result == ["collection1", "collection2"]

    def test_discover_collections_exception(self):
        """Test _discover_collections when exception occurs."""
        service = SearchService()
        service._persister.read_folder_files = Mock(side_effect=Exception("IO Error"))

        result = service._discover_collections()

        assert result == []

    def test_get_default_indexer_success(self):
        """Test _get_default_indexer when manifest exists."""
        service = SearchService()

        manifest_data = {
            "indexers": [
                {"name": "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"},
                {"name": "indexer_FAISS_IndexFlatL2__embeddings_all-mpnet-base-v2"},
            ]
        }

        service._persister.read_text_file = Mock(return_value=json.dumps(manifest_data))

        result = service._get_default_indexer("test-collection")

        assert result == "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"
        service._persister.read_text_file.assert_called_once_with(
            "test-collection/manifest.json"
        )

    def test_get_default_indexer_exception(self):
        """Test _get_default_indexer when exception occurs."""
        service = SearchService()
        service._persister.read_text_file = Mock(
            side_effect=Exception("File not found")
        )

        result = service._get_default_indexer("test-collection")

        assert result == "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"

    @patch("main.services.search_service.create_collection_searcher")
    def test_search_with_configs(self, mock_factory):
        """Test search with explicit configs."""
        mock_searcher = Mock()
        mock_searcher.search.return_value = {
            "collectionName": "test-collection",
            "results": [{"title": "Test Result"}],
        }
        mock_factory.return_value = mock_searcher

        service = SearchService()

        configs = [
            SourceConfig(
                name="test-collection",
                type="localFiles",
                base_url_or_path="/tmp/test",
                indexer="test-indexer",
            )
        ]

        result = service.search(
            "test query",
            configs=configs,
            max_chunks=15,
            max_docs=5,
            include_full_text=True,
        )

        assert "test-collection" in result
        assert result["test-collection"]["collectionName"] == "test-collection"

        mock_searcher.search.assert_called_once_with(
            "test query",
            max_number_of_chunks=15,
            max_number_of_documents=5,
            include_text_content=True,
            include_all_chunks_content=False,
            include_matched_chunks_content=False,
        )

    @patch("main.services.search_service.create_collection_searcher")
    def test_search_auto_discovery(self, mock_factory):
        """Test search with auto-discovery (configs=None)."""
        mock_searcher = Mock()
        mock_searcher.search.return_value = {"results": []}
        mock_factory.return_value = mock_searcher

        service = SearchService()

        # Mock discovery methods
        service._discover_collections = Mock(
            return_value=["collection1", "collection2"]
        )
        service._get_default_indexer = Mock(return_value="default-indexer")

        result = service.search("test query", configs=None)

        assert "collection1" in result
        assert "collection2" in result
        assert mock_searcher.search.call_count == 2

    def test_search_defaults(self):
        """Test search applies correct defaults."""
        service = SearchService()

        # Mock to avoid actual search
        service._get_searcher = Mock()
        mock_searcher = Mock()
        mock_searcher.search.return_value = {"results": []}
        service._get_searcher.return_value = mock_searcher

        configs = [
            SourceConfig(
                name="test-collection",
                type="localFiles",
                base_url_or_path="/tmp/test",
                indexer="test-indexer",
            )
        ]

        # Test with no max_docs/max_chunks specified
        service.search("test query", configs=configs)

        # Should use defaults: max_docs=10, max_chunks=max_docs*3=30
        mock_searcher.search.assert_called_with(
            "test query",
            max_number_of_chunks=30,  # 10 * 3
            max_number_of_documents=10,
            include_text_content=False,
            include_all_chunks_content=False,
            include_matched_chunks_content=False,
        )

    @patch("main.services.search_service.create_collection_searcher")
    def test_search_error_handling(self, mock_factory):
        """Test search handles errors gracefully."""
        mock_searcher = Mock()
        mock_searcher.search.side_effect = Exception("Search failed")
        mock_factory.return_value = mock_searcher

        service = SearchService()

        configs = [
            SourceConfig(
                name="failing-collection",
                type="localFiles",
                base_url_or_path="/tmp/test",
                indexer="test-indexer",
            )
        ]

        with patch("logging.error"):  # Suppress error logging in test
            result = service.search("test query", configs=configs)

        assert "failing-collection" in result
        assert "error" in result["failing-collection"]
        assert "Search failed" in result["failing-collection"]["error"]


class TestSearchFunctionalInterface:
    """Test functional search interface."""

    @patch("main.services.search_service._default_service")
    def test_search_function_delegates_to_service(self, mock_service):
        """Test that search function delegates to default service."""
        mock_service.search.return_value = {"test": "result"}

        configs = [
            SourceConfig(
                name="test-collection",
                type="localFiles",
                base_url_or_path="/tmp/test",
                indexer="test-indexer",
            )
        ]

        result = search(
            "test query",
            configs=configs,
            max_chunks=20,
            max_docs=8,
            include_full_text=True,
            include_all_chunks=True,
            include_matched_chunks=True,
        )

        assert result == {"test": "result"}
        mock_service.search.assert_called_once_with(
            "test query",
            configs=configs,
            max_chunks=20,
            max_docs=8,
            include_full_text=True,
            include_all_chunks=True,
            include_matched_chunks=True,
        )

    @patch("main.services.search_service._default_service")
    def test_search_function_with_defaults(self, mock_service):
        """Test search function with default parameters."""
        mock_service.search.return_value = {}

        search("test query")

        mock_service.search.assert_called_once_with(
            "test query",
            configs=None,
            max_chunks=None,
            max_docs=None,
            include_full_text=False,
            include_all_chunks=False,
            include_matched_chunks=False,
        )
