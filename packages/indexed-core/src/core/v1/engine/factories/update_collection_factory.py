"""Factory for creating collection updaters.

This module creates DocumentCollectionCreator instances configured for
update operations. It reads the collection manifest to reconstruct
the connector and applies date filters for incremental updates.
"""

import os
from datetime import datetime, timedelta
import json
from typing import Tuple, Any

from core.v1.engine.persisters.disk_persister import DiskPersister
from core.v1.engine.indexes.indexer_factory import load_indexer
from core.v1.engine.core.documents_collection_creator import (
    DocumentCollectionCreator,
    OPERATION_TYPE,
)
from connectors import get_connector_class, get_config_class

from utils.performance import log_execution_duration


def create_collection_updater(collection_name: str, progress_callback=None):
    """Create a collection updater for incremental updates.
    
    Args:
        collection_name: Name of the collection to update
        progress_callback: Optional callback for progress updates
        
    Returns:
        DocumentCollectionCreator configured for UPDATE operation
    """
    return log_execution_duration(
        lambda: _create_collection_updater(collection_name, progress_callback),
        identifier="Preparing collection updater",
    )


def _create_collection_updater(collection_name: str, progress_callback=None):
    """Internal implementation of collection updater creation."""
    disk_persister = DiskPersister(base_path="./data/collections")

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
    
    This function uses the connector registry to dynamically create the
    appropriate reader and converter based on the stored connector type.
    It builds a config DTO from the manifest data and environment variables.
    
    Args:
        manifest: Collection manifest containing reader configuration
        
    Returns:
        Tuple of (reader, converter) instances
        
    Raises:
        ValueError: If connector type is unknown or credentials are missing
    """
    connector_type = manifest["reader"]["type"]
    
    try:
        connector_cls = get_connector_class(connector_type)
        config_cls = get_config_class(connector_type)
    except ValueError as e:
        raise ValueError(f"Unknown document reader type: {connector_type}") from e
    
    # Build config DTO from manifest + environment variables
    config_dto = _build_config_from_manifest(manifest, connector_type, config_cls)
    
    # Create connector using from_dto pattern
    connector = connector_cls.from_dto(config_dto)
    
    return connector.reader, connector.converter


def _build_config_from_manifest(
    manifest: dict,
    connector_type: str,
    config_cls: type
) -> Any:
    """Build config DTO from manifest data and environment variables.
    
    Args:
        manifest: Collection manifest
        connector_type: Type of connector
        config_cls: Pydantic config class for the connector
        
    Returns:
        Populated config DTO instance
    """
    reader_config = manifest["reader"]
    update_date = _calculate_update_date(manifest).isoformat()
    
    # Build base config dict from manifest
    config_dict = {}
    
    if connector_type == "jira":
        config_dict = _build_jira_config(reader_config, update_date)
    elif connector_type == "jiraCloud":
        config_dict = _build_jira_cloud_config(reader_config, update_date)
    elif connector_type == "confluence":
        config_dict = _build_confluence_config(reader_config, update_date)
    elif connector_type == "confluenceCloud":
        config_dict = _build_confluence_cloud_config(reader_config, update_date)
    elif connector_type == "localFiles":
        config_dict = _build_local_files_config(reader_config, manifest)
    else:
        raise ValueError(f"Cannot build config for type: {connector_type}")
    
    return config_cls(**config_dict)


def _build_jira_config(reader_config: dict, update_date: str) -> dict:
    """Build Jira Server/DC config from manifest."""
    query_addition = f'AND (created >= "{update_date}" OR updated >= "{update_date}")'
    
    return {
        "url": reader_config["baseUrl"],
        "query": f"{reader_config['query']} {query_addition}",
        "token": os.environ.get("JIRA_TOKEN"),
        "login": os.environ.get("JIRA_LOGIN"),
        "password": os.environ.get("JIRA_PASSWORD"),
    }


def _build_jira_cloud_config(reader_config: dict, update_date: str) -> dict:
    """Build Jira Cloud config from manifest."""
    email = os.environ.get("ATLASSIAN_EMAIL")
    api_token = os.environ.get("ATLASSIAN_TOKEN")
    
    if not email or not api_token:
        raise ValueError(
            "Both 'ATLASSIAN_EMAIL' and 'ATLASSIAN_TOKEN' environment variables "
            "must be provided for Jira Cloud."
        )
    
    query_addition = f'AND (created >= "{update_date}" OR updated >= "{update_date}")'
    
    return {
        "url": reader_config["baseUrl"],
        "query": f"{reader_config['query']} {query_addition}",
        "email": email,
        "api_token": api_token,
    }


def _build_confluence_config(reader_config: dict, update_date: str) -> dict:
    """Build Confluence Server/DC config from manifest."""
    token = os.environ.get("CONF_TOKEN")
    login = os.environ.get("CONF_LOGIN")
    password = os.environ.get("CONF_PASSWORD")
    
    if not token and (not login or not password):
        raise ValueError(
            "Either 'CONF_TOKEN' or both 'CONF_LOGIN' and 'CONF_PASSWORD' "
            "environment variables must be provided for Confluence."
        )
    
    query_addition = f'AND (created >= "{update_date}" OR lastModified >= "{update_date}")'
    
    return {
        "url": reader_config["baseUrl"],
        "query": f"{reader_config['query']} {query_addition}",
        "token": token,
        "login": login,
        "password": password,
        "read_all_comments": reader_config.get("readAllComments", True),
    }


def _build_confluence_cloud_config(reader_config: dict, update_date: str) -> dict:
    """Build Confluence Cloud config from manifest."""
    email = os.environ.get("ATLASSIAN_EMAIL")
    api_token = os.environ.get("ATLASSIAN_TOKEN")
    
    if not email or not api_token:
        raise ValueError(
            "Both 'ATLASSIAN_EMAIL' and 'ATLASSIAN_TOKEN' environment variables "
            "must be provided for Confluence Cloud."
        )
    
    query_addition = f'AND (created >= "{update_date}" OR lastModified >= "{update_date}")'
    
    return {
        "url": reader_config["baseUrl"],
        "query": f"{reader_config['query']} {query_addition}",
        "email": email,
        "api_token": api_token,
        "read_all_comments": reader_config.get("readAllComments", True),
    }


def _build_local_files_config(reader_config: dict, manifest: dict) -> dict:
    """Build local files config from manifest.
    
    Note: Incremental updates for local files are not fully supported via
    the connector pattern. The start_from_time filtering would need to be
    added to the LocalFilesConfig schema for full support.
    """
    # TODO: Add start_from_time to LocalFilesConfig for incremental file updates
    # update_time = _calculate_update_time(manifest)
    
    return {
        "path": reader_config["basePath"],
        "include_patterns": reader_config.get("includePatterns", [".*"]),
        "exclude_patterns": reader_config.get("excludePatterns", []),
        "fail_fast": reader_config.get("failFast", False),
    }
