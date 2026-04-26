"""Factory for creating collection updaters.

This module creates DocumentCollectionCreator instances configured for
update operations. It reads the collection manifest to reconstruct
the connector and applies date filters for incremental updates.

Uses the same from_config() pattern as create operations for unified
config handling across the CLI.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
import json
from typing import Any

from core.v1.engine.persisters.disk_persister import DiskPersister
from core.v1.engine.indexes.indexer_factory import load_indexer
from core.v1.engine.core.documents_collection_creator import (
    DocumentCollectionCreator,
    OPERATION_TYPE,
)
from core.v1.config_models import get_default_collections_path

from utils.performance import log_execution_duration


def create_collection_updater(
    collection_name: str,
    progress_callback=None,
    phased_progress=None,
    collections_path: str | None = None,
):
    """Create a collection updater for incremental updates.

    Args:
        collection_name: Name of the collection to update
        progress_callback: Optional callback for progress updates
        phased_progress: Optional PhasedProgressCallback for multi-stage display.
        collections_path: Optional path for collections storage.
                         Defaults to resolved path from storage config.

    Returns:
        DocumentCollectionCreator configured for UPDATE operation
    """
    return log_execution_duration(
        lambda: _create_collection_updater(
            collection_name, progress_callback, phased_progress, collections_path
        ),
        identifier="Preparing collection updater",
    )


def _create_collection_updater(
    collection_name: str,
    progress_callback=None,
    phased_progress=None,
    collections_path: str | None = None,
):
    """Internal implementation of collection updater creation."""
    resolved_path = collections_path or str(get_default_collections_path())
    disk_persister = DiskPersister(base_path=resolved_path)

    if not disk_persister.is_path_exists(collection_name):
        raise ValueError(f"Collection {collection_name} does not exist")

    manifest = json.loads(
        disk_persister.read_text_file(f"{collection_name}/manifest.json")
    )

    connector_type = manifest["reader"]["type"]
    post_run = None

    if connector_type == "localFiles":
        document_reader, document_converter, explicit_deletions, post_run = (
            _build_local_files_update(manifest, collection_name, disk_persister)
        )
    else:
        document_reader, document_converter = _create_reader_and_converter(manifest)
        explicit_deletions = []

    document_indexers = [
        load_indexer(indexer["name"], collection_name, disk_persister)
        for indexer in manifest["indexers"]
    ]

    creator = DocumentCollectionCreator(
        collection_name=collection_name,
        document_reader=document_reader,
        document_converter=document_converter,
        document_indexers=document_indexers,
        persister=disk_persister,
        operation_type=OPERATION_TYPE.UPDATE,
        progress_callback=progress_callback,
        phased_progress=phased_progress,
        explicit_deletions=explicit_deletions,
    )

    if post_run is not None:
        return _UpdatingCollectionCreator(creator, post_run)
    return creator


class _UpdatingCollectionCreator:
    """Thin wrapper: runs a DocumentCollectionCreator then calls a post-run hook.

    Used to persist ChangeTracker state after a successful update without
    modifying the DocumentCollectionCreator interface.
    """

    def __init__(
        self, creator: DocumentCollectionCreator, post_run: Callable[[], None]
    ) -> None:
        self._creator = creator
        self._post_run = post_run

    def run(self) -> None:
        self._creator.run()
        self._post_run()


def _calculate_update_time(manifest: dict) -> datetime:
    """Calculate the update cutoff time from manifest."""
    return datetime.fromisoformat(manifest["lastModifiedDocumentTime"]) - timedelta(
        days=1
    )


def _calculate_update_date(manifest: dict):
    """Calculate the update cutoff date from manifest."""
    return _calculate_update_time(manifest).date()


def _create_reader_and_converter(manifest: dict) -> tuple[Any, Any]:
    """Create reader and converter from manifest using connector registry.

    This function uses the same from_config() pattern as create operations,
    ensuring unified config handling across the CLI. It:
    1. Creates a ConfigService instance
    2. Populates it with values from the manifest and environment variables
    3. Calls connector.from_config(config_service)

    Args:
        manifest: Collection manifest containing reader configuration

    Returns:
        Tuple of (reader, converter) instances

    Raises:
        ValueError: If connector type is unknown or credentials are missing
    """
    from indexed_config import ConfigService
    from connectors import get_connector_class, get_config_namespace

    connector_type = manifest["reader"]["type"]

    try:
        connector_cls = get_connector_class(connector_type)
        namespace = get_config_namespace(connector_type)
    except ValueError as e:
        raise ValueError(f"Unknown document reader type: {connector_type}") from e

    # Create ConfigService and populate with manifest values
    # This mirrors the pattern used in collection_service._build_connector_from_config()
    config_service = ConfigService()
    _populate_config_from_manifest(config_service, manifest, connector_type, namespace)

    # Create connector using the unified from_config() pattern
    connector = connector_cls.from_config(config_service)

    return connector.reader, connector.converter


def _populate_config_from_manifest(
    config_service: Any,
    manifest: dict,
    connector_type: str,
    namespace: str,
) -> None:
    """Populate ConfigService with values from manifest.

    This function sets config values in the ConfigService based on the
    connector type and manifest data. Credentials are read from environment
    variables by the connector's from_config() method.

    Args:
        config_service: ConfigService instance to populate
        manifest: Collection manifest
        connector_type: Type of connector (e.g., "jira", "confluenceCloud")
        namespace: Config namespace for this connector (e.g., "sources.jira")
    """
    reader_config = manifest["reader"]
    update_date = _calculate_update_date(manifest).isoformat()

    if connector_type == "jira":
        _populate_jira_config(config_service, reader_config, namespace, update_date)
    elif connector_type == "jiraCloud":
        _populate_jira_cloud_config(
            config_service, reader_config, namespace, update_date
        )
    elif connector_type == "confluence":
        _populate_confluence_config(
            config_service, reader_config, namespace, update_date
        )
    elif connector_type == "confluenceCloud":
        _populate_confluence_cloud_config(
            config_service, reader_config, namespace, update_date
        )
    elif connector_type == "localFiles":
        _populate_local_files_config(config_service, reader_config, namespace)
    else:
        raise ValueError(f"Cannot populate config for type: {connector_type}")


def _populate_jira_config(
    config_service: Any,
    reader_config: dict,
    namespace: str,
    update_date: str,
) -> None:
    """Populate ConfigService with Jira Server/DC config from manifest."""
    query_addition = f'AND (created >= "{update_date}" OR updated >= "{update_date}")'

    config_service.set(f"{namespace}.url", reader_config["baseUrl"])
    config_service.set(
        f"{namespace}.query", f"{reader_config['query']} {query_addition}"
    )
    # Credentials are read from env vars by the connector's from_config() method


def _populate_jira_cloud_config(
    config_service: Any,
    reader_config: dict,
    namespace: str,
    update_date: str,
) -> None:
    """Populate ConfigService with Jira Cloud config from manifest."""
    query_addition = f'AND (created >= "{update_date}" OR updated >= "{update_date}")'

    config_service.set(f"{namespace}.url", reader_config["baseUrl"])
    config_service.set(
        f"{namespace}.query", f"{reader_config['query']} {query_addition}"
    )
    # Credentials (email, api_token) are read from env vars by from_config()


def _populate_confluence_config(
    config_service: Any,
    reader_config: dict,
    namespace: str,
    update_date: str,
) -> None:
    """Populate ConfigService with Confluence Server/DC config from manifest."""
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
    # Credentials are read from env vars by the connector's from_config() method


def _populate_confluence_cloud_config(
    config_service: Any,
    reader_config: dict,
    namespace: str,
    update_date: str,
) -> None:
    """Populate ConfigService with Confluence Cloud config from manifest."""
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
    # Credentials (email, api_token) are read from env vars by from_config()


def _populate_local_files_config(
    config_service: Any,
    reader_config: dict,
    namespace: str,
) -> None:
    """Populate ConfigService with local files config from manifest."""
    config_service.set(f"{namespace}.path", reader_config["basePath"])
    config_service.set(
        f"{namespace}.include_patterns", reader_config.get("includePatterns", [".*"])
    )
    config_service.set(f"{namespace}.fail_fast", reader_config.get("failFast", False))
    config_service.set(
        f"{namespace}.respect_gitignore", reader_config.get("respectGitignore", True)
    )


def _build_local_files_update(
    manifest: dict,
    collection_name: str,
    disk_persister: DiskPersister,
) -> tuple[Any, Any, list[str], Callable[[], None]]:
    """Build reader, converter, deletions, and post-run hook for a localFiles update.

    Uses ChangeTracker to detect which files changed since the last index run,
    limiting the reader to only those files.

    Returns:
        (reader, converter, explicit_deletions, post_run_callback)
    """
    from connectors.files.connector import FileSystemConnector
    from connectors.files.files_document_reader import FilesDocumentReader

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
        # No prior state — full re-index (first update after create without state)
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
