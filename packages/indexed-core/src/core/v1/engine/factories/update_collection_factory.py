"""Factory for creating collection updaters.

This module creates DocumentCollectionCreator instances configured for
update operations. It reads the collection manifest to reconstruct
the connector and applies date filters for incremental updates.

Uses the same from_config() pattern as create operations for unified
config handling across the CLI.
"""

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Optional, Tuple, Any

from core.v1.engine.persisters.disk_persister import DiskPersister
from core.v1.engine.indexes.indexer_factory import load_indexer
from core.v1.engine.core.documents_collection_creator import (
    DocumentCollectionCreator,
    OPERATION_TYPE,
)
from connectors import get_connector_class, get_config_namespace

from utils.performance import log_execution_duration


def _get_default_collections_path() -> str:
    """Get the default collections path from storage config."""
    try:
        from indexed_config import get_resolver
        resolver = get_resolver()
        return str(resolver.get_collections_path())
    except ImportError:
        # Fallback if indexed_config not available
        return str(Path.home() / ".indexed" / "data" / "collections")


def create_collection_updater(
    collection_name: str,
    progress_callback=None,
    collections_path: Optional[str] = None,
):
    """Create a collection updater for incremental updates.
    
    Args:
        collection_name: Name of the collection to update
        progress_callback: Optional callback for progress updates
        collections_path: Optional path for collections storage.
                         Defaults to resolved path from storage config.
        
    Returns:
        DocumentCollectionCreator configured for UPDATE operation
    """
    return log_execution_duration(
        lambda: _create_collection_updater(
            collection_name, progress_callback, collections_path
        ),
        identifier="Preparing collection updater",
    )


def _create_collection_updater(
    collection_name: str,
    progress_callback=None,
    collections_path: Optional[str] = None,
):
    """Internal implementation of collection updater creation."""
    resolved_path = collections_path or _get_default_collections_path()
    disk_persister = DiskPersister(base_path=resolved_path)

    if not disk_persister.is_path_exists(collection_name):
        raise ValueError(f"Collection {collection_name} does not exist")

    manifest = json.loads(
        disk_persister.read_text_file(f"{collection_name}/manifest.json")
    )

    document_reader, document_converter = _create_reader_and_converter(manifest)

    document_indexers = [
        load_indexer(indexer["name"], collection_name, disk_persister)
        for indexer in manifest["indexers"]
    ]

    return DocumentCollectionCreator(
        collection_name=collection_name,
        document_reader=document_reader,
        document_converter=document_converter,
        document_indexers=document_indexers,
        persister=disk_persister,
        operation_type=OPERATION_TYPE.UPDATE,
        progress_callback=progress_callback,
    )


def _calculate_update_time(manifest: dict) -> datetime:
    """Calculate the update cutoff time from manifest."""
    return datetime.fromisoformat(manifest["lastModifiedDocumentTime"]) - timedelta(
        days=1
    )


def _calculate_update_date(manifest: dict):
    """Calculate the update cutoff date from manifest."""
    return _calculate_update_time(manifest).date()


def _create_reader_and_converter(manifest: dict) -> Tuple[Any, Any]:
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
        _populate_jira_cloud_config(config_service, reader_config, namespace, update_date)
    elif connector_type == "confluence":
        _populate_confluence_config(config_service, reader_config, namespace, update_date)
    elif connector_type == "confluenceCloud":
        _populate_confluence_cloud_config(config_service, reader_config, namespace, update_date)
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
    config_service.set(f"{namespace}.query", f"{reader_config['query']} {query_addition}")
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
    config_service.set(f"{namespace}.query", f"{reader_config['query']} {query_addition}")
    # Credentials (email, api_token) are read from env vars by from_config()


def _populate_confluence_config(
    config_service: Any,
    reader_config: dict,
    namespace: str,
    update_date: str,
) -> None:
    """Populate ConfigService with Confluence Server/DC config from manifest."""
    query_addition = f'AND (created >= "{update_date}" OR lastModified >= "{update_date}")'
    
    config_service.set(f"{namespace}.url", reader_config["baseUrl"])
    config_service.set(f"{namespace}.query", f"{reader_config['query']} {query_addition}")
    config_service.set(
        f"{namespace}.read_all_comments",
        reader_config.get("readAllComments", True)
    )
    # Credentials are read from env vars by the connector's from_config() method


def _populate_confluence_cloud_config(
    config_service: Any,
    reader_config: dict,
    namespace: str,
    update_date: str,
) -> None:
    """Populate ConfigService with Confluence Cloud config from manifest."""
    query_addition = f'AND (created >= "{update_date}" OR lastModified >= "{update_date}")'
    
    config_service.set(f"{namespace}.url", reader_config["baseUrl"])
    config_service.set(f"{namespace}.query", f"{reader_config['query']} {query_addition}")
    config_service.set(
        f"{namespace}.read_all_comments",
        reader_config.get("readAllComments", True)
    )
    # Credentials (email, api_token) are read from env vars by from_config()


def _populate_local_files_config(
    config_service: Any,
    reader_config: dict,
    namespace: str,
) -> None:
    """Populate ConfigService with local files config from manifest.
    
    Note: Incremental updates for local files are not fully supported via
    the connector pattern. The start_from_time filtering would need to be
    added to the LocalFilesConfig schema for full support.
    """
    config_service.set(f"{namespace}.path", reader_config["basePath"])
    config_service.set(
        f"{namespace}.include_patterns",
        reader_config.get("includePatterns", [".*"])
    )
    config_service.set(
        f"{namespace}.exclude_patterns",
        reader_config.get("excludePatterns", [])
    )
    config_service.set(
        f"{namespace}.fail_fast",
        reader_config.get("failFast", False)
    )
