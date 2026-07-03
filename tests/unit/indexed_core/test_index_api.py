"""Tests for core.v1.Index public API edge paths."""

from unittest.mock import MagicMock, patch

import pytest
from protocols import BaseConnector

from core.v1.index import Index, IndexConfig


class _FakeConnector:
    connector_type = "localFiles"

    @property
    def reader(self):
        return MagicMock()

    @property
    def converter(self):
        return MagicMock()


def test_add_collection_rejects_non_protocol_connector() -> None:
    index = Index()
    with pytest.raises(TypeError, match="BaseConnector"):
        index.add_collection("bad", connector=object())  # type: ignore[arg-type]


def test_add_collection_runs_creator() -> None:
    index = Index()
    connector = MagicMock(spec=BaseConnector)
    connector.reader = MagicMock()
    connector.converter = MagicMock()
    connector.connector_type = "localFiles"
    with patch("core.v1.index.create_collection_creator") as mock_create:
        mock_creator = MagicMock()
        mock_create.return_value = mock_creator
        index.add_collection("docs", connector=connector)
        mock_creator.run.assert_called_once()
        assert "docs" in index._collections


def test_search_with_named_collection_builds_config() -> None:
    index = Index()
    mock_status = MagicMock()
    mock_status.indexers = ["idx1"]
    with (
        patch("core.v1.index.status", return_value=[mock_status]),
        patch("core.v1.index.search", return_value={"docs": []}) as mock_search,
    ):
        index.search("query", collection="docs", max_results=3)

    mock_search.assert_called_once()
    configs = mock_search.call_args.kwargs["configs"]
    assert configs[0].name == "docs"
    assert configs[0].indexer == "idx1"


def test_update_tracked_collection_calls_service() -> None:
    index = Index()
    index._collections["docs"] = _FakeConnector()  # type: ignore[assignment]
    with patch("core.v1.index.update") as mock_update:
        index.update("docs")
    mock_update.assert_called_once()
    assert mock_update.call_args[0][0][0].name == "docs"


def test_update_untracked_collection_uses_factory() -> None:
    index = Index()
    mock_updater = MagicMock()
    with (
        patch("core.v1.index.status", return_value=[MagicMock(name="docs")]),
        patch(
            "core.v1.engine.factories.update_collection_factory.create_collection_updater",
            return_value=mock_updater,
        ),
    ):
        index.update("docs")
    mock_updater.run.assert_called_once()


def test_update_all_runs_tracked_and_discovered() -> None:
    index = Index()
    index._collections["tracked"] = _FakeConnector()  # type: ignore[assignment]
    mock_updater = MagicMock()
    discovered = MagicMock()
    discovered.name = "other"
    with (
        patch("core.v1.index.update") as mock_update,
        patch("core.v1.index.status", return_value=[discovered]),
        patch(
            "core.v1.engine.factories.update_collection_factory.create_collection_updater",
            return_value=mock_updater,
        ),
    ):
        index.update()
    mock_update.assert_called_once()
    mock_updater.run.assert_called_once()


def test_index_list_collections_tracks_added() -> None:
    index = Index()
    connector = MagicMock(spec=BaseConnector)
    connector.reader = MagicMock()
    connector.converter = MagicMock()
    connector.connector_type = "localFiles"
    with patch("core.v1.index.create_collection_creator") as mock_create:
        mock_create.return_value = MagicMock()
        index.add_collection("docs", connector=connector)
    assert index.list_collections() == ["docs"]


def test_index_remove_deletes_tracked_collection() -> None:
    index = Index()
    index._collections["docs"] = MagicMock()
    with patch("core.v1.index.clear") as mock_clear:
        index.remove("docs")
    mock_clear.assert_called_once_with(["docs"])
    assert "docs" not in index._collections


def test_index_status_single_and_all() -> None:
    index = Index()
    with patch(
        "core.v1.index.status", return_value=[MagicMock(name="docs")]
    ) as mock_status:
        index.status("docs")
        mock_status.assert_called_with(["docs"])
    with patch("core.v1.index.status", return_value=[]) as mock_status:
        index.status()
        mock_status.assert_called_once_with()


def test_index_config_default_indexer() -> None:
    assert IndexConfig().default_indexer.startswith("indexer_FAISS")
