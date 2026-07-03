"""Temporary connector wiring for app layer until bootstrap.py lands in /3."""

from __future__ import annotations

from typing import Any, Callable

from indexed_config.errors import ConfigurationError
from protocols import SourceConfig

from core.v1.engine.persisters.disk_persister import DiskPersister


def build_connector_from_source_config(cfg: SourceConfig, config_service: Any) -> Any:
    """Build connector from SourceConfig — moved from core collection_service."""
    from connectors.confluence import ConfluenceCloudConnector, ConfluenceConnector
    from connectors.files import FileSystemConnector
    from connectors.jira import JiraCloudConnector, JiraConnector
    from connectors.outline import OutlineConnector

    if cfg.type == "jira":
        config_service.set("sources.jira.url", cfg.base_url_or_path)
        config_service.set("sources.jira.query", cfg.query)
        for key, value in cfg.reader_opts.items():
            config_service.set(f"sources.jira.{key}", value)
        return JiraConnector.from_config(config_service)

    if cfg.type == "jiraCloud":
        config_service.set("sources.jira.url", cfg.base_url_or_path)
        config_service.set("sources.jira.query", cfg.query)
        for key, value in cfg.reader_opts.items():
            config_service.set(f"sources.jira.{key}", value)
        return JiraCloudConnector.from_config(config_service)

    if cfg.type == "confluence":
        config_service.set("sources.confluence.url", cfg.base_url_or_path)
        config_service.set("sources.confluence.query", cfg.query)
        for key, value in cfg.reader_opts.items():
            config_service.set(f"sources.confluence.{key}", value)
        return ConfluenceConnector.from_config(config_service)

    if cfg.type == "confluenceCloud":
        config_service.set("sources.confluence.url", cfg.base_url_or_path)
        config_service.set("sources.confluence.query", cfg.query)
        for key, value in cfg.reader_opts.items():
            config_service.set(f"sources.confluence.{key}", value)
        return ConfluenceCloudConnector.from_config(config_service)

    if cfg.type == "localFiles":
        config_service.set("sources.files.path", cfg.base_url_or_path)
        if "includePatterns" in cfg.reader_opts:
            config_service.set(
                "sources.files.include_patterns", cfg.reader_opts["includePatterns"]
            )
        if "failFast" in cfg.reader_opts:
            config_service.set("sources.files.fail_fast", cfg.reader_opts["failFast"])
        if "respectGitignore" in cfg.reader_opts:
            config_service.set(
                "sources.files.respect_gitignore", cfg.reader_opts["respectGitignore"]
            )
        return FileSystemConnector.from_config(config_service)

    if cfg.type == "outline":
        config_service.set("sources.outline.url", cfg.base_url_or_path)
        opts = cfg.reader_opts
        if opts.get("collectionIds") is not None:
            config_service.set("sources.outline.collection_ids", opts["collectionIds"])
        if "includeAttachments" in opts:
            config_service.set(
                "sources.outline.include_attachments", opts["includeAttachments"]
            )
        if "ocrEnabled" in opts:
            config_service.set("sources.outline.ocr_enabled", opts["ocrEnabled"])
        return OutlineConnector.from_config(config_service)

    raise ValueError(f"Unknown source type: {cfg.type}")


def make_connector_factory(config_service: Any) -> Callable[[SourceConfig], Any]:
    return lambda cfg: build_connector_from_source_config(cfg, config_service)


def make_cache_decorator_factory() -> Callable[[Any, DiskPersister], Any]:
    from connectors.document_cache_reader_decorator import CacheReaderDecorator

    def factory(reader: Any, persister: DiskPersister) -> Any:
        return CacheReaderDecorator(reader=reader, persister=persister)

    return factory


def make_manifest_connector_factory() -> Callable[[dict], tuple[Any, Any]]:
    from indexed_config import ConfigService

    from core.v1.engine.factories import update_collection_factory as ucf

    def factory(manifest: dict) -> tuple[Any, Any]:
        from connectors import get_config_namespace, get_connector_class

        connector_type = manifest["reader"]["type"]
        connector_cls = get_connector_class(connector_type)
        namespace = get_config_namespace(connector_type)
        config_service = ConfigService()
        ucf._populate_config_from_manifest(
            config_service, manifest, connector_type, namespace
        )
        return _connector_reader_converter_from_manifest(
            manifest, connector_type, connector_cls, config_service
        )

    return factory


def _connector_reader_converter_from_manifest(
    manifest: dict,
    connector_type: str,
    connector_cls: Any,
    config_service: Any,
) -> tuple[Any, Any]:
    import os

    from core.v1.engine.factories.update_collection_factory import (
        _OUTLINE_MODIFIED_SINCE_ENV,
    )

    outline_cutoff_set = False
    if connector_type == "outline":
        last_modified = manifest.get("lastModifiedDocumentTime")
        if last_modified is None:
            raise ValueError(
                "Manifest is missing 'lastModifiedDocumentTime' required for "
                "Outline incremental update"
            )
        os.environ[_OUTLINE_MODIFIED_SINCE_ENV] = last_modified
        outline_cutoff_set = True

    try:
        connector = connector_cls.from_config(config_service)
    finally:
        if outline_cutoff_set:
            os.environ.pop(_OUTLINE_MODIFIED_SINCE_ENV, None)

    return connector.reader, connector.converter


def make_local_files_update_factory() -> Callable[
    [dict, str, DiskPersister], tuple[Any, Any, list[str], Callable[[], None] | None]
]:
    from connectors.files.connector import FileSystemConnector
    from connectors.files.files_document_reader import FilesDocumentReader

    def factory(
        manifest: dict,
        collection_name: str,
        disk_persister: DiskPersister,
    ) -> tuple[Any, Any, list[str], Callable[[], None] | None]:
        reader_config = manifest["reader"]
        connector = FileSystemConnector(
            path=reader_config["basePath"],
            include_patterns=reader_config.get("includePatterns") or ["*"],
            fail_fast=reader_config.get("failFast", False),
            change_tracking=reader_config.get("changeTracking", "auto"),
            excluded_dirs=reader_config.get("excludedDirs") or None,
            respect_gitignore=reader_config.get("respectGitignore", True),
        )

        collection_full_path = disk_persister.get_full_path(collection_name)
        state = connector.load_state(collection_full_path)

        if state is not None:
            changed_paths = connector.get_files_to_process(state)
            deleted_files: list[str] = connector.get_deletions(state)
            specific_files: list[str] | None = [str(p) for p in changed_paths]
        else:
            specific_files = None
            deleted_files = []

        cfg = connector._config
        reader = FilesDocumentReader(
            base_path=connector._path,
            include_patterns=connector._include_patterns,
            fail_fast=connector._fail_fast,
            ocr=cfg.ocr_enabled,
            table_structure=cfg.table_structure,
            max_tokens=cfg.max_chunk_tokens,
            excluded_dirs=cfg.excluded_dirs or None,
            specific_files=specific_files,
            respect_gitignore=cfg.respect_gitignore,
        )

        def _save_state() -> None:
            connector.save_state(collection_full_path)

        return reader, connector.converter, deleted_files, _save_state

    return factory


def wiring_kwargs_for_create(config_service: Any) -> dict[str, Any]:
    return {
        "connector_factory": make_connector_factory(config_service),
        "cache_decorator_factory": make_cache_decorator_factory(),
    }


def wiring_kwargs_for_update() -> dict[str, Any]:
    return {
        "manifest_connector_factory": make_manifest_connector_factory(),
        "local_files_update_factory": make_local_files_update_factory(),
    }


def missing_wiring_error(component: str) -> ConfigurationError:
    return ConfigurationError(
        f"{component} must be injected by the app layer; "
        "see indexed.connector_wiring (bootstrap in /3)"
    )
