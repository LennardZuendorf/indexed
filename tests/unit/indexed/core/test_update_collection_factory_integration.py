"""Integration tests for update collection factory with on-disk manifest."""

import json
from unittest.mock import MagicMock, patch

import pytest

from indexed.core.v1.engine.factories.update_collection_factory import (
    create_collection_updater,
)
from indexed.protocols import ConnectorRun


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
        "indexed.core.v1.engine.factories.update_collection_factory.load_indexer"
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
def test_create_collection_updater_corrupt_manifest_raises_clean_error(
    tmp_path,
) -> None:
    """A manifest missing a required field surfaces a clean, mapped error.

    A raw pydantic ``ValidationError`` (or JSON error) would otherwise reach the
    CLI as a traceback; the factory wraps it in a clear message naming the
    collection. The message match distinguishes it from a bare ValidationError
    (which is itself a ``ValueError`` subclass).
    """
    from pydantic import ValidationError

    coll = "broken-docs"
    coll_dir = tmp_path / coll
    coll_dir.mkdir()
    # numberOfChunks (a required Manifest field) is intentionally omitted.
    manifest = {
        "collectionName": coll,
        "updatedTime": "2026-07-07T00:00:00+00:00",
        "lastModifiedDocumentTime": "2026-07-05T00:00:00+00:00",
        "numberOfDocuments": 1,
        "reader": {"type": "localFiles", "basePath": str(tmp_path)},
        "indexers": [{"name": "faiss-flat-l2"}],
    }
    (coll_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid or corrupt manifest") as excinfo:
        create_collection_updater(
            coll, collections_path=str(tmp_path), manifest_factory=MagicMock()
        )

    assert coll in str(excinfo.value)
    # It must be the wrapped error, not the raw pydantic ValidationError.
    assert not isinstance(excinfo.value, ValidationError)


@pytest.mark.unit
def test_creator_runs_post_hook_after_successful_run() -> None:
    """The connector's post_run hook fires after a successful run().

    Replaces the old ``_UpdatingCollectionCreator`` wrapper: the post-run hook
    now lives on ``DocumentCollectionCreator`` itself and is invoked at the end
    of ``run()`` once the create/update operation succeeds.
    """
    from indexed.core.v1.engine.core.documents_collection_creator import (
        OPERATION_TYPE,
        DocumentCollectionCreator,
    )

    post = MagicMock()
    creator = DocumentCollectionCreator(
        collection_name="c",
        document_reader=MagicMock(),
        document_converter=MagicMock(),
        document_indexers=[MagicMock()],
        persister=MagicMock(),
        operation_type=OPERATION_TYPE.CREATE,
        post_run=post,
    )

    with patch.object(
        creator, "_DocumentCollectionCreator__create_collection"
    ) as mock_create:
        creator.run()

    mock_create.assert_called_once()
    post.assert_called_once()
