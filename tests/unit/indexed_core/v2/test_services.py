"""Tests for core.v2.services — collection, search, and inspect services."""

from unittest.mock import MagicMock, patch

import pytest

from core.v2.services.collection_service import clear, create, update
from core.v2.services.inspect_service import inspect, status
from core.v2.services.search_service import SearchService, search
from core.v2.storage import write_manifest


# --- Collection service tests ---


class TestCollectionCreate:
    """create() delegates to ingestion.create_collection."""

    @patch("core.v2.ingestion.create_collection")
    def test_delegates_to_ingestion(self, mock_create: MagicMock) -> None:
        mock_create.return_value = {"name": "col"}
        connector = MagicMock()

        result = create("col", connector)

        mock_create.assert_called_once()
        assert result["name"] == "col"

    @patch("core.v2.ingestion.create_collection")
    def test_passes_kwargs(self, mock_create: MagicMock) -> None:
        mock_create.return_value = {}
        create(
            "col",
            MagicMock(),
            embed_model_name="custom-model",
            store_type="faiss",
        )
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["embed_model_name"] == "custom-model"
        assert call_kwargs["store_type"] == "faiss"


class TestCollectionUpdate:
    """update() removes and recreates the collection."""

    @patch("core.v2.ingestion.create_collection")
    def test_delegates_to_create(self, mock_create: MagicMock) -> None:
        mock_create.return_value = {"name": "col"}
        result = update("col", MagicMock())
        assert result["name"] == "col"


class TestCollectionClear:
    """clear() removes collections from disk."""

    def test_removes_existing(self, tmp_path) -> None:
        col_dir = tmp_path / "col"
        col_dir.mkdir()
        (col_dir / "manifest.json").write_text("{}")

        removed = clear(["col"], collections_dir=tmp_path)
        assert removed == ["col"]
        assert not col_dir.exists()

    def test_nonexistent_skipped(self, tmp_path) -> None:
        removed = clear(["nope"], collections_dir=tmp_path)
        assert removed == []

    def test_mixed(self, tmp_path) -> None:
        (tmp_path / "a").mkdir()
        removed = clear(["a", "b"], collections_dir=tmp_path)
        assert removed == ["a"]


# --- Inspect service tests ---


class TestStatus:
    """status() reads manifests and returns CollectionStatus."""

    def test_single_collection(self, tmp_path) -> None:
        write_manifest("col", num_documents=5, num_chunks=20, collections_dir=tmp_path)

        result = status(["col"], collections_dir=tmp_path)
        assert len(result) == 1
        assert result[0].name == "col"
        assert result[0].number_of_documents == 5
        assert result[0].number_of_chunks == 20

    def test_auto_discover(self, tmp_path) -> None:
        write_manifest("a", num_documents=1, num_chunks=1, collections_dir=tmp_path)
        write_manifest("b", num_documents=2, num_chunks=2, collections_dir=tmp_path)

        result = status(collections_dir=tmp_path)
        assert len(result) == 2
        names = {s.name for s in result}
        assert names == {"a", "b"}

    def test_missing_collection_skipped(self, tmp_path) -> None:
        result = status(["nonexistent"], collections_dir=tmp_path)
        assert result == []


class TestInspect:
    """inspect() returns detailed CollectionInfo."""

    def test_basic(self, tmp_path) -> None:
        write_manifest(
            "col",
            num_documents=3,
            num_chunks=15,
            source_type="localFiles",
            collections_dir=tmp_path,
        )

        info = inspect("col", collections_dir=tmp_path)
        assert info.name == "col"
        assert info.number_of_documents == 3
        assert info.number_of_chunks == 15
        assert info.source_type == "localFiles"
        assert info.disk_size_bytes > 0


# --- Search service tests ---


class TestSearchFunction:
    """search() stateless function."""

    @patch("core.v2.retrieval.search_collection")
    def test_single_collection_via_config(self, mock_search: MagicMock) -> None:
        from core.v2.services.models import SourceConfig

        mock_search.return_value = {"collectionName": "col", "results": []}
        config = SourceConfig(name="col", type="localFiles", base_url_or_path=".")

        result = search("test query", configs=[config])

        mock_search.assert_called_once()
        assert result["collectionName"] == "col"

    @patch("core.v2.storage.list_collection_names")
    @patch("core.v2.retrieval.search_collection")
    def test_auto_discover_multiple(
        self, mock_search: MagicMock, mock_list: MagicMock
    ) -> None:
        mock_list.return_value = ["a", "b"]
        mock_search.side_effect = [
            {"collectionName": "a", "results": []},
            {"collectionName": "b", "results": []},
        ]

        result = search("query")
        assert "collections" in result
        assert len(result["collections"]) == 2


class TestSearchService:
    """SearchService stateful class."""

    @patch("core.v2.retrieval.search_collection")
    def test_search_specific_collection(self, mock_search: MagicMock) -> None:
        mock_search.return_value = {"collectionName": "col", "results": []}
        svc = SearchService()

        result = svc.search("query", collection_name="col")
        assert result["collectionName"] == "col"

    @patch("core.v2.storage.list_collection_names")
    @patch("core.v2.retrieval.search_collection")
    def test_search_all_collections(
        self, mock_search: MagicMock, mock_list: MagicMock
    ) -> None:
        mock_list.return_value = ["a"]
        mock_search.return_value = {"collectionName": "a", "results": []}
        svc = SearchService()

        result = svc.search("query")
        assert "collections" in result
