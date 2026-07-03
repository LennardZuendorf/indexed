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

from indexed_config.errors import ConfigurationError

from core.v1.engine.persisters.disk_persister import DiskPersister
from core.v1.engine.indexes.indexer_factory import load_indexer
from core.v1.engine.core.documents_collection_creator import (
    DocumentCollectionCreator,
    OPERATION_TYPE,
)
from core.v1.config_models import get_default_collections_path

from utils.performance import log_execution_duration

_OUTLINE_MODIFIED_SINCE_ENV = "INDEXED__sources__outline__modified_since"


def create_collection_updater(
    collection_name: str,
    progress_callback=None,
    phased_progress=None,
    collections_path: str | None = None,
    manifest_connector_factory: Callable[[dict], tuple[Any, Any]] | None = None,
    local_files_update_factory: Callable[
        [dict, str, DiskPersister],
        tuple[Any, Any, list[str], Callable[[], None] | None],
    ]
    | None = None,
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
            collection_name,
            progress_callback,
            phased_progress,
            collections_path,
            manifest_connector_factory,
            local_files_update_factory,
        ),
        identifier="Preparing collection updater",
    )


def _create_collection_updater(
    collection_name: str,
    progress_callback=None,
    phased_progress=None,
    collections_path: str | None = None,
    manifest_connector_factory: Callable[[dict], tuple[Any, Any]] | None = None,
    local_files_update_factory: Callable[
        [dict, str, DiskPersister],
        tuple[Any, Any, list[str], Callable[[], None] | None],
    ]
    | None = None,
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
        if local_files_update_factory is None:
            raise ConfigurationError(
                "local_files_update_factory must be injected by the app layer; "
                "see indexed.bootstrap"
            )
        document_reader, document_converter, explicit_deletions, post_run = (
            local_files_update_factory(manifest, collection_name, disk_persister)
        )
    else:
        document_reader, document_converter = _create_reader_and_converter(
            manifest, manifest_connector_factory
        )
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


def _create_reader_and_converter(
    manifest: dict,
    manifest_connector_factory: Callable[[dict], tuple[Any, Any]] | None = None,
) -> tuple[Any, Any]:
    """Create reader and converter from manifest via injected factory."""
    if manifest_connector_factory is None:
        raise ConfigurationError(
            "manifest_connector_factory must be injected by the app layer; "
            "see indexed.bootstrap"
        )
    return manifest_connector_factory(manifest)


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
    elif connector_type == "outline":
        _populate_outline_config(config_service, reader_config, namespace)
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


def _populate_outline_config(
    config_service: Any,
    reader_config: dict,
    namespace: str,
) -> None:
    """Populate ConfigService with Outline config from manifest."""
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
    # api_token read from OUTLINE_API_TOKEN env var by from_config()


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
