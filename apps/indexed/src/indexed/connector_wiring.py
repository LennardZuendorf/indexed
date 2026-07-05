"""App-layer connector wiring for create/update command paths."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable

from indexed_config.service import ConfigService
from protocols import BaseConnector, SourceConfig

from core.v1.engine.persisters.disk_persister import DiskPersister

from .bootstrap import build_connector
from .runtime import CliContext

_OUTLINE_MODIFIED_SINCE_ENV = "INDEXED__sources__outline__modified_since"


def make_connector_factory(ctx: CliContext) -> Callable[[SourceConfig], BaseConnector]:
    """Build connectors via bootstrap using context registry."""
    return lambda cfg: build_connector(cfg, ctx.config_service, ctx.connector_registry)


def make_cache_decorator_factory() -> Callable[[Any, DiskPersister], Any]:
    from connectors.document_cache_reader_decorator import CacheReaderDecorator

    def factory(reader: Any, persister: DiskPersister) -> Any:
        return CacheReaderDecorator(reader=reader, persister=persister)

    return factory


def _calculate_update_time(manifest: dict) -> datetime:
    return datetime.fromisoformat(manifest["lastModifiedDocumentTime"]) - timedelta(
        days=1
    )


def _calculate_update_date(manifest: dict) -> date:
    return _calculate_update_time(manifest).date()


def _populate_jira_config(
    config_service: ConfigService,
    reader_config: dict,
    namespace: str,
    update_date: str,
) -> None:
    query_addition = f'AND (created >= "{update_date}" OR updated >= "{update_date}")'
    config_service.set(f"{namespace}.url", reader_config["baseUrl"])
    config_service.set(
        f"{namespace}.query", f"{reader_config['query']} {query_addition}"
    )


def _populate_confluence_config(
    config_service: ConfigService,
    reader_config: dict,
    namespace: str,
    update_date: str,
) -> None:
    query_addition = (
        f'AND (created >= "{update_date}" OR lastModified >= "{update_date}")'
    )
    config_service.set(f"{namespace}.url", reader_config["baseUrl"])
    config_service.set(
        f"{namespace}.query", f"{reader_config['query']} {query_addition}"
    )
    config_service.set(
        f"{namespace}.read_all_comments", reader_config.get("readAllComments", True)
    )


def _populate_outline_config(
    config_service: ConfigService,
    reader_config: dict,
    namespace: str,
) -> None:
    config_service.set(f"{namespace}.url", reader_config["baseUrl"])
    if reader_config.get("collectionIds") is not None:
        config_service.set(
            f"{namespace}.collection_ids", reader_config["collectionIds"]
        )
    config_service.set(
        f"{namespace}.include_attachments",
        reader_config.get("includeAttachments", True),
    )
    if reader_config.get("batchSize") is not None:
        config_service.set(f"{namespace}.batch_size", reader_config["batchSize"])
    if reader_config.get("ocrEnabled") is not None:
        config_service.set(f"{namespace}.ocr_enabled", reader_config["ocrEnabled"])
    if reader_config.get("downloadInlineImages") is not None:
        config_service.set(
            f"{namespace}.download_inline_images", reader_config["downloadInlineImages"]
        )
    if reader_config.get("maxConcurrentRequests") is not None:
        config_service.set(
            f"{namespace}.max_concurrent_requests",
            reader_config["maxConcurrentRequests"],
        )
    if reader_config.get("maxAttachmentSizeMb") is not None:
        config_service.set(
            f"{namespace}.max_attachment_size_mb", reader_config["maxAttachmentSizeMb"]
        )
    if reader_config.get("verifySsl") is not None:
        config_service.set(f"{namespace}.verify_ssl", reader_config["verifySsl"])


def _populate_local_files_config(
    config_service: ConfigService,
    reader_config: dict,
    namespace: str,
) -> None:
    config_service.set(f"{namespace}.path", reader_config["basePath"])
    config_service.set(
        f"{namespace}.include_patterns", reader_config.get("includePatterns", [".*"])
    )
    config_service.set(f"{namespace}.fail_fast", reader_config.get("failFast", False))
    config_service.set(
        f"{namespace}.respect_gitignore", reader_config.get("respectGitignore", True)
    )


def populate_config_from_manifest(
    config_service: ConfigService,
    manifest: dict,
    connector_type: str,
    namespace: str,
) -> None:
    """Populate ConfigService with values from manifest for incremental updates."""
    reader_config = manifest["reader"]
    update_date = _calculate_update_date(manifest).isoformat()

    if connector_type in ("jira", "jiraCloud"):
        _populate_jira_config(config_service, reader_config, namespace, update_date)
    elif connector_type in ("confluence", "confluenceCloud"):
        _populate_confluence_config(
            config_service, reader_config, namespace, update_date
        )
    elif connector_type == "localFiles":
        _populate_local_files_config(config_service, reader_config, namespace)
    elif connector_type == "outline":
        _populate_outline_config(config_service, reader_config, namespace)
    else:
        raise ValueError(f"Cannot populate config for type: {connector_type}")


def _connector_reader_converter_from_manifest(
    manifest: dict,
    connector_type: str,
    connector_cls: Any,
    config_service: ConfigService,
) -> tuple[Any, Any]:
    import os

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


def make_manifest_connector_factory(
    ctx: CliContext,
) -> Callable[[dict], tuple[Any, Any]]:
    from connectors import get_config_namespace, get_connector_class

    def factory(manifest: dict) -> tuple[Any, Any]:
        connector_type = manifest["reader"]["type"]
        connector_cls = get_connector_class(connector_type)
        namespace = get_config_namespace(connector_type)
        populate_config_from_manifest(
            ctx.config_service, manifest, connector_type, namespace
        )
        return _connector_reader_converter_from_manifest(
            manifest, connector_type, connector_cls, ctx.config_service
        )

    return factory


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


def wiring_kwargs_for_create(ctx: CliContext) -> dict[str, Any]:
    return {
        "connector_factory": make_connector_factory(ctx),
        "cache_decorator_factory": make_cache_decorator_factory(),
    }


def wiring_kwargs_for_update(ctx: CliContext) -> dict[str, Any]:
    return {
        "manifest_connector_factory": make_manifest_connector_factory(ctx),
        "local_files_update_factory": make_local_files_update_factory(),
    }
