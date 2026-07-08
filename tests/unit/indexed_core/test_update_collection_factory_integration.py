"""Integration tests for update collection factory with on-disk manifest."""

import json
from unittest.mock import MagicMock, patch

import pytest

from protocols import ConnectorRun
from core.v1.engine.factories.update_collection_factory import create_collection_updater


@pytest.mark.unit
def test_create_collection_updater_uses_manifest_factory(tmp_path) -> None:
    coll = "my-docs"
    coll_dir = tmp_path / coll
    coll_dir.mkdir()
    manifest = {
        "collectionName": coll,
        "updatedTime": "2026-07-07T00:00:00+00:00",
        "lastModifiedDocumentTime": "2026-07-05T00:00:00+00:00",
        "numberOfDocuments": 1,
        "numberOfChunks": 1,
        "reader": {
            "type": "localFiles",
            "basePath": str(tmp_path / "source"),
            "includePatterns": ["*.txt"],
            "failFast": False,
            "changeTracking": "auto",
            "respectGitignore": False,
        },
        "indexers": [
            {"name": "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"}
        ],
    }
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "a.txt").write_text("hi", encoding="utf-8")
    (coll_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    mock_reader = MagicMock()
    mock_converter = MagicMock()
    manifest_factory = MagicMock(
        return_value=ConnectorRun(mock_reader, mock_converter, [], None)
    )

    with patch(
        "core.v1.engine.factories.update_collection_factory.load_indexer"
    ) as mock_load:
        mock_load.return_value = MagicMock()
        updater = create_collection_updater(
            coll,
            collections_path=str(tmp_path),
            manifest_factory=manifest_factory,
        )

    manifest_factory.assert_called_once()
    call_args = manifest_factory.call_args
    # called with (Manifest, storage_path)
    assert call_args[0][0].reader.type == "localFiles"
    assert coll in call_args[0][1]
    assert updater.document_reader is mock_reader
    assert updater.document_converter is mock_converter


@pytest.mark.unit
def test_create_collection_updater_missing_collection_raises(tmp_path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        create_collection_updater(
            "missing", collections_path=str(tmp_path), manifest_factory=MagicMock()
        )


@pytest.mark.unit
def test_updating_collection_creator_runs_post_hook() -> None:
    from core.v1.engine.factories.update_collection_factory import (
        _UpdatingCollectionCreator,
    )

    inner = MagicMock()
    post = MagicMock()
    wrapper = _UpdatingCollectionCreator(inner, post)
    wrapper.run()
    inner.run.assert_called_once()
    post.assert_called_once()
