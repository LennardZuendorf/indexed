"""Tests for search service."""

from unittest.mock import Mock, patch

import pytest

from indexed.config.errors import StorageError
from indexed.core.v1.engine.services.models import SourceConfig
from indexed.core.v1.engine.services.search_service import SearchService, search


class TestSearchService:
    """Test SearchService class."""

    def test_init(self):
        """Test initialization."""
        service = SearchService()

        assert service._persister is not None
        assert service._searcher_cache == {}

    @patch("indexed.core.v1.engine.services.search_service.create_collection_searcher")
    def test_get_searcher_creates_new(self, mock_factory):
        """Test _get_searcher creates new searcher when not cached."""
        mock_searcher = Mock()
        mock_factory.return_value = mock_searcher

        service = SearchService()

        searcher = service._get_searcher(
            collection_name="test-collection", index_name="test-indexer"
        )

        assert searcher == mock_searcher
        mock_factory.assert_called_once()
        # Verify the key arguments (collections_path may vary based on config)
        call_kwargs = mock_factory.call_args.kwargs
        assert call_kwargs["collection_name"] == "test-collection"
        assert call_kwargs["index_name"] == "test-indexer"

    @patch("indexed.core.v1.engine.services.search_service.create_collection_searcher")
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
                "not-a-collection/data.json",
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

    @patch("indexed.core.v1.engine.services.search_service.create_collection_searcher")
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

        # Verify searcher creation (collections_path may vary based on config)
        mock_factory.assert_called_once()
        call_kwargs = mock_factory.call_args.kwargs
        assert call_kwargs["collection_name"] == "test-collection"
        assert call_kwargs["index_name"] == "test-indexer"

        # Verify search parameters (implementation uses 'text' not 'query')
        mock_searcher.search.assert_called_once_with(
            text="test query",
            max_number_of_chunks=10,
            max_number_of_documents=5,
            include_text_content=True,
            include_all_chunks_content=True,
            include_matched_chunks_content=True,
        )

    @patch("indexed.core.v1.engine.services.search_service.create_collection_searcher")
    def test_search_with_score_threshold_overfetches_and_backfills(self, mock_factory):
        """A5: when score_threshold is set, the searcher must be asked for more
        than max_docs documents so that documents dropped by the filter can be
        backfilled from the next-best surviving ones, then the final result is
        truncated back to max_docs (filter-before-truncate + backfill)."""
        mock_searcher = Mock()
        # 4 candidate docs ranked best (lowest score) to worst; rank-1 fails
        # the threshold, so rank-4 must backfill into the top-2 result.
        mock_searcher.search.return_value = {
            "results": [
                {"id": "doc-1", "matchedChunks": [{"score": 3.0}]},  # filtered out
                {"id": "doc-2", "matchedChunks": [{"score": 0.5}]},
                {"id": "doc-3", "matchedChunks": [{"score": 0.6}]},
                {"id": "doc-4", "matchedChunks": [{"score": 0.7}]},
            ]
        }
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
            max_docs=2,
            score_threshold=1.0,
        )

        # Searcher must be over-fetched (more than the requested max_docs=2)
        # so filtering has candidates left to backfill from.
        call_kwargs = mock_searcher.search.call_args.kwargs
        assert call_kwargs["max_number_of_documents"] > 2

        # Final result is truncated to max_docs AFTER filtering: doc-1 is
        # dropped by the threshold and doc-3 backfills its slot.
        doc_ids = [doc["id"] for doc in result["test-collection"]["results"]]
        assert doc_ids == ["doc-2", "doc-3"]

    @patch("indexed.core.v1.engine.services.search_service.create_collection_searcher")
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

        # Verify searcher creation with discovered collection (collections_path may vary)
        mock_factory.assert_called_once()
        call_kwargs = mock_factory.call_args.kwargs
        assert call_kwargs["collection_name"] == "collection1"
        assert (
            call_kwargs["index_name"]
            == "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"
        )

        # Verify search parameters (implementation uses 'text' not 'query')
        mock_searcher.search.assert_called_once_with(
            text="test query",
            max_number_of_chunks=10,
            max_number_of_documents=5,
            include_text_content=True,
            include_all_chunks_content=True,
            include_matched_chunks_content=True,
        )

    @patch("indexed.core.v1.engine.services.search_service.create_collection_searcher")
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


class TestDiscoverCollectionsFailsLoud:
    """A directory-scan I/O error must fail loud, not silently return zero
    collections (tech.md "fail loud, never zero-filled"). Per-collection
    search errors (search() try/except) stay tolerated — only the top-level
    scan swallow is the bug."""

    def test_discover_collections_raises_on_scan_error(self):
        service = SearchService()
        service._persister.read_folder_files = Mock(
            side_effect=OSError("permission denied")
        )

        with pytest.raises(StorageError, match="permission denied"):
            service._discover_collections()

    def test_discover_collections_returns_empty_on_missing_dir(self, tmp_path):
        """R3: a fresh install with no collections directory yet must not
        crash the MCP ``search`` tool (auto-discover path) — a missing top
        dir (ENOENT) is a normal, empty state, not a scan failure."""
        service = SearchService(collections_path=str(tmp_path / "does-not-exist"))

        assert service._discover_collections() == []

    def test_discover_collections_filters_staging_dirs(self):
        """R3: internal build-aside staging dirs (``<name>.tmp-<pid>-<hex>``)
        must never surface as discovered collections — this filter already
        exists in InspectService._discover_collections but was missing here."""
        service = SearchService()
        service._persister.read_folder_files = Mock(
            return_value=[
                "mycol.tmp-12345-abcd1234/manifest.json",
                "real/manifest.json",
            ]
        )
        service._persister.is_path_exists = Mock(return_value=True)

        result = service._discover_collections()

        assert result == ["real"]


class TestSearchFunctionalInterface:
    """Test functional search interface."""

    @patch("indexed.core.v1.engine.services.search_service.SearchService")
    def test_search_function_delegates_to_service(self, mock_service_cls):
        """Test that search function delegates to a per-call service."""
        mock_service = mock_service_cls.return_value
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
        )

    @patch("indexed.core.v1.engine.services.search_service.SearchService")
    def test_search_function_with_defaults(self, mock_service_cls):
        """Test search function with default parameters."""
        mock_service = mock_service_cls.return_value
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
        )
