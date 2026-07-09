"""Tests for app-layer connector wiring helpers.

The update path is now a single ``manifest_factory`` that dispatches to each
connector's ``from_manifest`` (the per-connector query/overlay behavior it
replaced is tested in tests/unit/indexed_connectors/test_from_manifest.py).
"""

from unittest.mock import MagicMock, patch

from protocols import ConnectorRun, Manifest

from indexed.composition import (
    make_cache_decorator_factory,
    make_connector_factory,
    make_manifest_factory,
    wiring_kwargs_for_create,
    wiring_kwargs_for_update,
)
from indexed.composition import CliContext


def _manifest(connector_type: str = "jira") -> Manifest:
    return Manifest.from_disk(
        {
            "collectionName": "c",
            "updatedTime": "2026-03-16T00:00:00+00:00",
            "lastModifiedDocumentTime": "2026-03-15T10:00:00+00:00",
            "numberOfDocuments": 1,
            "numberOfChunks": 1,
            "reader": {
                "type": connector_type,
                "baseUrl": "https://example.com",
                "query": "project = X",
            },
            "indexers": [{"name": "faiss-flat-l2"}],
        }
    )


def test_make_connector_factory_delegates_to_build_connector() -> None:
    ctx = MagicMock(spec=CliContext)
    ctx.config_service = MagicMock()
    ctx.connector_registry = {"jira": MagicMock()}
    cfg = MagicMock()

    with patch("indexed.composition.build_connector", return_value="conn") as mock:
        factory = make_connector_factory(ctx)
        assert factory(cfg) == "conn"
        mock.assert_called_once_with(cfg, ctx.config_service, ctx.connector_registry)


def test_make_cache_decorator_factory_wraps_reader() -> None:
    from connectors.document_cache_reader_decorator import CacheReaderDecorator

    reader = MagicMock()
    persister = MagicMock()
    factory = make_cache_decorator_factory()
    result = factory(reader, persister)
    assert isinstance(result, CacheReaderDecorator)


def test_wiring_kwargs_keys() -> None:
    ctx = MagicMock(spec=CliContext)
    create_keys = wiring_kwargs_for_create(ctx)
    update_keys = wiring_kwargs_for_update(ctx)
    assert set(create_keys) == {"connector_factory", "cache_decorator_factory"}
    assert set(update_keys) == {"manifest_factory"}


def test_make_manifest_factory_dispatches_to_from_manifest() -> None:
    ctx = MagicMock(spec=CliContext)
    ctx.config_service = MagicMock()
    manifest = _manifest("jira")
    run = ConnectorRun(reader="R", converter="C", deletions=[], post_run=None)
    connector_cls = MagicMock(from_manifest=MagicMock(return_value=run))

    with patch("connectors.get_connector_class", return_value=connector_cls):
        factory = make_manifest_factory(ctx)
        result = factory(manifest, "/storage/coll")

    assert result is run
    connector_cls.from_manifest.assert_called_once_with(
        manifest, ctx.config_service, storage_path="/storage/coll"
    )
