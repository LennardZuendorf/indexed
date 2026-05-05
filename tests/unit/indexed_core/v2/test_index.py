"""Tests for core.v2.index — Index facade."""

from unittest.mock import MagicMock, patch

import pytest

from core.v2 import Index, IndexConfig


class TestIndexConfig:
    """IndexConfig holds v2 configuration defaults."""

    def test_defaults(self) -> None:
        cfg = IndexConfig()
        assert cfg.embed_model_name == "all-MiniLM-L6-v2"
        assert cfg.vector_store_type == "faiss"

    def test_custom(self) -> None:
        cfg = IndexConfig(embed_model_name="custom", vector_store_type="chroma")
        assert cfg.embed_model_name == "custom"
        assert cfg.vector_store_type == "chroma"


class TestIndex:
    """Index facade delegates to services."""

    @patch("core.v2.ingestion.create_collection")
    def test_add_collection(self, mock_create: MagicMock) -> None:
        mock_create.return_value = {"name": "docs"}
        index = Index()
        connector = MagicMock()

        result = index.add_collection("docs", connector)

        mock_create.assert_called_once()
        assert result["name"] == "docs"
        assert "docs" in index.list_collections()

    @patch("core.v2.retrieval.search_collection")
    def test_search_specific_collection(self, mock_search: MagicMock) -> None:
        mock_search.return_value = {"collectionName": "docs", "results": []}
        index = Index()

        result = index.search("query", collection="docs")

        assert result["collectionName"] == "docs"

    @patch("core.v2.storage.list_collection_names")
    @patch("core.v2.retrieval.search_collection")
    def test_search_all(self, mock_search: MagicMock, mock_list: MagicMock) -> None:
        mock_list.return_value = ["a"]
        mock_search.return_value = {"collectionName": "a", "results": []}
        index = Index()

        result = index.search("query")
        assert result["collectionName"] == "a"

    @patch("core.v2.ingestion.create_collection")
    def test_update_tracked(self, mock_create: MagicMock) -> None:
        mock_create.return_value = {"name": "docs"}
        index = Index()
        connector = MagicMock()
        index._collections["docs"] = connector

        index.update("docs")
        mock_create.assert_called_once()

    def test_update_unknown_collection_raises(self) -> None:
        from core.v2.errors import CollectionNotFoundError

        index = Index()
        with pytest.raises(CollectionNotFoundError, match="ghost"):
            index.update("ghost")

    @patch("core.v2.storage.read_manifest")
    def test_status_single(self, mock_read: MagicMock) -> None:
        mock_read.return_value = {
            "name": "docs",
            "num_documents": 5,
            "num_chunks": 20,
            "updated_time": "2026-01-01",
            "embed_model_name": "all-MiniLM-L6-v2",
            "source_type": "localFiles",
        }
        index = Index()
        result = index.status("docs")
        assert result is not None
        assert result.name == "docs"

    def test_remove(self, tmp_path) -> None:
        col_dir = tmp_path / "docs"
        col_dir.mkdir()
        (col_dir / "manifest.json").write_text("{}")

        with patch("core.v2.storage.get_collections_dir", return_value=tmp_path):
            index = Index()
            index._collections["docs"] = MagicMock()
            index.remove("docs")

            assert "docs" not in index.list_collections()
            assert not col_dir.exists()

    def test_list_collections_empty(self) -> None:
        index = Index()
        assert index.list_collections() == []


class TestNoImportSideEffects:
    """Importing core.v2 must not trigger config registration or heavy imports."""

    def test_version(self) -> None:
        import core.v2

        assert core.v2.__version__ == "2.0.0"

    def test_exports(self) -> None:
        from core.v2 import Index, IndexConfig

        assert Index is not None
        assert IndexConfig is not None
