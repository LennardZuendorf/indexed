"""Tests for app-layer connector wiring helpers."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from indexed.connector_wiring import (
    _calculate_update_date,
    _populate_confluence_cloud_config,
    _populate_confluence_config,
    _populate_jira_cloud_config,
    _populate_jira_config,
    _populate_local_files_config,
    make_cache_decorator_factory,
    make_connector_factory,
    make_local_files_update_factory,
    make_manifest_connector_factory,
    missing_wiring_error,
    populate_config_from_manifest,
    wiring_kwargs_for_create,
    wiring_kwargs_for_update,
)
from indexed.runtime import CliContext


def _manifest(connector_type: str, reader: dict | None = None) -> dict:
    base_reader = {
        "type": connector_type,
        "baseUrl": "https://example.com",
        "query": "project = X",
    }
    if reader:
        base_reader.update(reader)
    return {
        "reader": base_reader,
        "lastModifiedDocumentTime": "2026-03-15T10:00:00+00:00",
        "indexers": [{"name": "FAISS"}],
    }


@pytest.mark.parametrize(
    ("connector_type", "populate_fn", "namespace"),
    [
        ("jira", _populate_jira_config, "sources.jira"),
        ("jiraCloud", _populate_jira_cloud_config, "sources.jira"),
        ("confluence", _populate_confluence_config, "sources.confluence"),
        ("confluenceCloud", _populate_confluence_cloud_config, "sources.confluence"),
    ],
)
def test_populate_cloud_configs_add_date_filter(
    connector_type, populate_fn, namespace
) -> None:
    config_service = MagicMock()
    reader = {"baseUrl": "https://example.com", "query": "type = page"}
    update_date = "2026-03-14"

    populate_fn(config_service, reader, namespace, update_date)

    config_service.set.assert_any_call(f"{namespace}.url", reader["baseUrl"])
    query_call = [
        c for c in config_service.set.call_args_list if c.args[0].endswith(".query")
    ]
    assert query_call
    assert update_date in query_call[0].args[1]


def test_populate_local_files_config_sets_path_and_patterns() -> None:
    config_service = MagicMock()
    reader = {
        "basePath": "/data/docs",
        "includePatterns": ["*.md"],
        "failFast": True,
        "respectGitignore": False,
    }

    _populate_local_files_config(config_service, reader, "sources.files")

    config_service.set.assert_any_call("sources.files.path", "/data/docs")
    config_service.set.assert_any_call("sources.files.include_patterns", ["*.md"])
    config_service.set.assert_any_call("sources.files.fail_fast", True)
    config_service.set.assert_any_call("sources.files.respect_gitignore", False)


@pytest.mark.parametrize(
    "connector_type",
    ["jira", "jiraCloud", "confluence", "confluenceCloud", "localFiles", "outline"],
)
def test_populate_config_from_manifest_dispatches(connector_type: str) -> None:
    config_service = MagicMock()
    manifest = _manifest(
        connector_type,
        reader={
            "basePath": "/tmp",
            "includePatterns": [".*"],
        }
        if connector_type == "localFiles"
        else None,
    )

    populate_config_from_manifest(
        config_service, manifest, connector_type, f"sources.{connector_type}"
    )

    assert config_service.set.called


def test_populate_config_from_manifest_unknown_type_raises() -> None:
    with pytest.raises(ValueError, match="Cannot populate config"):
        populate_config_from_manifest(MagicMock(), _manifest("unknown"), "unknown", "x")


def test_calculate_update_date_subtracts_one_day() -> None:
    manifest = {"lastModifiedDocumentTime": "2026-03-15T10:00:00+00:00"}
    assert _calculate_update_date(manifest) == date(2026, 3, 14)


def test_make_connector_factory_delegates_to_build_connector() -> None:
    ctx = MagicMock(spec=CliContext)
    ctx.config_service = MagicMock()
    ctx.connector_registry = {"jira": MagicMock()}
    cfg = MagicMock()

    with patch("indexed.connector_wiring.build_connector", return_value="conn") as mock:
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
    assert "connector_factory" in create_keys
    assert "cache_decorator_factory" in create_keys
    assert "manifest_connector_factory" in update_keys
    assert "local_files_update_factory" in update_keys


def test_missing_wiring_error_message() -> None:
    err = missing_wiring_error("manifest_connector_factory")
    assert "manifest_connector_factory" in str(err)
    assert "bootstrap" in str(err)


def test_make_manifest_connector_factory(tmp_path: Path) -> None:
    ctx = MagicMock(spec=CliContext)
    ctx.config_service = MagicMock()
    manifest = _manifest("jira")
    mock_reader = MagicMock()
    mock_converter = MagicMock()
    mock_connector = MagicMock(reader=mock_reader, converter=mock_converter)

    with (
        patch(
            "connectors.get_connector_class",
            return_value=MagicMock(from_config=MagicMock(return_value=mock_connector)),
        ),
        patch("connectors.get_config_namespace", return_value="sources.jira"),
        patch(
            "indexed.connector_wiring.populate_config_from_manifest",
        ) as mock_populate,
    ):
        factory = make_manifest_connector_factory(ctx)
        reader, converter = factory(manifest)

    mock_populate.assert_called_once()
    assert reader is mock_reader
    assert converter is mock_converter


def test_populate_outline_config_optional_fields() -> None:
    from indexed.connector_wiring import _populate_outline_config

    config_service = MagicMock()
    reader = {
        "baseUrl": "https://outline.example.com",
        "downloadInlineImages": False,
        "maxConcurrentRequests": 4,
        "maxAttachmentSizeMb": 10,
        "verifySsl": False,
    }
    _populate_outline_config(config_service, reader, "sources.outline")
    config_service.set.assert_any_call("sources.outline.download_inline_images", False)
    config_service.set.assert_any_call("sources.outline.max_concurrent_requests", 4)
    config_service.set.assert_any_call("sources.outline.max_attachment_size_mb", 10)
    config_service.set.assert_any_call("sources.outline.verify_ssl", False)


def test_connector_reader_converter_outline_missing_timestamp_raises() -> None:
    from indexed.connector_wiring import _connector_reader_converter_from_manifest

    manifest = {"reader": {"type": "outline"}}
    with pytest.raises(ValueError, match="lastModifiedDocumentTime"):
        _connector_reader_converter_from_manifest(
            manifest, "outline", MagicMock(), MagicMock()
        )


def test_populate_confluence_config_read_all_comments_false() -> None:
    config_service = MagicMock()
    reader = {
        "baseUrl": "https://wiki.example.com",
        "query": "space = DEV",
        "readAllComments": False,
    }
    _populate_confluence_config(
        config_service, reader, "sources.confluence", "2026-01-01"
    )
    config_service.set.assert_any_call("sources.confluence.read_all_comments", False)


def test_make_local_files_update_factory_without_state(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("hello", encoding="utf-8")
    manifest = {
        "reader": {
            "type": "localFiles",
            "basePath": str(docs),
            "includePatterns": ["*.md"],
            "failFast": False,
            "changeTracking": "auto",
            "respectGitignore": True,
        }
    }
    persister = MagicMock()
    persister.get_full_path.return_value = str(tmp_path / "collection")

    factory = make_local_files_update_factory()
    reader, converter, deleted, post_run = factory(manifest, "coll", persister)

    assert reader is not None
    assert converter is not None
    assert deleted == []
    assert post_run is not None
