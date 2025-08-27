"""Collection service for managing document collections.

This module provides functionality to create, update, and manage document collections
from various sources including Confluence, Jira, and local files. It handles the
orchestration of readers, converters, and persisters to build searchable collections.
"""

import os
from typing import List, Tuple
from .models import SourceConfig
from ..utils.logger import setup_root_logger
from ..persisters.disk_persister import DiskPersister
from ..factories.create_collection_factory import create_collection_creator
from ..factories.update_collection_factory import create_collection_updater

# Import all the readers and converters we need
from ..sources.confluence.confluence_document_reader import ConfluenceDocumentReader
from ..sources.confluence.confluence_document_converter import (
    ConfluenceDocumentConverter,
)
from ..sources.confluence.confluence_cloud_document_reader import (
    ConfluenceCloudDocumentReader,
)
from ..sources.confluence.confluence_cloud_document_converter import (
    ConfluenceCloudDocumentConverter,
)
from ..sources.jira.jira_document_reader import JiraDocumentReader
from ..sources.jira.jira_document_converter import JiraDocumentConverter
from ..sources.jira.jira_cloud_document_reader import JiraCloudDocumentReader
from ..sources.jira.jira_cloud_document_converter import JiraCloudDocumentConverter
from ..sources.files.files_document_reader import FilesDocumentReader
from ..sources.files.files_document_converter import FilesDocumentConverter

setup_root_logger()


def _build_reader_converter(cfg: SourceConfig) -> Tuple:
    """Build reader and converter based on source config type.

    This function creates the appropriate document reader and converter pair
    based on the source configuration type. It handles authentication setup
    for each source type using environment variables.

    Args:
        cfg (SourceConfig): Source configuration containing type, URL, query, and options.

    Returns:
        Tuple: A tuple containing (reader, converter) instances for the specified source type.

    Raises:
        ValueError: If required environment variables are missing or if source type is unknown.

    Note:
        This reuses the exact same logic from the legacy adapter scripts.

        Environment variables required by source type:
        - confluence: CONF_TOKEN or (CONF_LOGIN and CONF_PASSWORD)
        - confluenceCloud: ATLASSIAN_EMAIL and ATLASSIAN_TOKEN
        - jira: JIRA_TOKEN or (JIRA_LOGIN and JIRA_PASSWORD)
        - jiraCloud: ATLASSIAN_EMAIL and ATLASSIAN_TOKEN
        - localFiles: No authentication required
    """
    if cfg.type == "confluence":
        # Confluence Server/Data Center setup
        token = os.environ.get("CONF_TOKEN")
        login = os.environ.get("CONF_LOGIN")
        password = os.environ.get("CONF_PASSWORD")

        if not token and (not login or not password):
            raise ValueError(
                "Either 'token' ('CONF_TOKEN' env variable) or both 'login' ('CONF_LOGIN' env variable) and 'password' ('CONF_PASSWORD' env variable) must be provided."
            )

        reader = ConfluenceDocumentReader(
            base_url=cfg.base_url_or_path,
            query=cfg.query,
            token=token,
            login=login,
            password=password,
            read_all_comments=(
                not cfg.reader_opts.get("readOnlyFirstLevelComments", False)
            ),
        )
        converter = ConfluenceDocumentConverter()
        return reader, converter

    elif cfg.type == "confluenceCloud":
        # Confluence Cloud setup
        email = os.environ.get("ATLASSIAN_EMAIL")
        api_token = os.environ.get("ATLASSIAN_TOKEN")

        if not email or not api_token:
            raise ValueError(
                "Both 'ATLASSIAN_EMAIL' and 'ATLASSIAN_TOKEN' environment variables must be provided for Confluence Cloud."
            )

        reader = ConfluenceCloudDocumentReader(
            base_url=cfg.base_url_or_path,
            query=cfg.query,
            email=email,
            api_token=api_token,
            read_all_comments=(
                not cfg.reader_opts.get("readOnlyFirstLevelComments", False)
            ),
        )
        converter = ConfluenceCloudDocumentConverter()
        return reader, converter

    elif cfg.type == "jira":
        # Jira Server/Data Center authentication
        token = os.environ.get("JIRA_TOKEN")
        login = os.environ.get("JIRA_LOGIN")
        password = os.environ.get("JIRA_PASSWORD")

        if not token and (not login or not password):
            raise ValueError(
                "Either 'token' ('JIRA_TOKEN' env variable) or both 'login' ('JIRA_LOGIN' env variable) and 'password' ('JIRA_PASSWORD' env variable) must be provided for Jira Server/Data Center."
            )

        reader = JiraDocumentReader(
            base_url=cfg.base_url_or_path,
            query=cfg.query,
            token=token,
            login=login,
            password=password,
        )
        converter = JiraDocumentConverter()
        return reader, converter

    elif cfg.type == "jiraCloud":
        # Jira Cloud authentication
        email = os.environ.get("ATLASSIAN_EMAIL")
        api_token = os.environ.get("ATLASSIAN_TOKEN")

        if not email or not api_token:
            raise ValueError(
                "Both 'ATLASSIAN_EMAIL' and 'ATLASSIAN_TOKEN' environment variables must be provided for Jira Cloud."
            )

        reader = JiraCloudDocumentReader(
            base_url=cfg.base_url_or_path,
            query=cfg.query,
            email=email,
            api_token=api_token,
        )
        converter = JiraCloudDocumentConverter()
        return reader, converter

    elif cfg.type == "localFiles":
        reader = FilesDocumentReader(
            base_path=cfg.base_url_or_path,
            include_patterns=cfg.reader_opts.get("includePatterns", [".*"]),
            exclude_patterns=cfg.reader_opts.get("excludePatterns", []),
            fail_fast=cfg.reader_opts.get("failFast", False),
        )
        converter = FilesDocumentConverter()
        return reader, converter

    else:
        raise ValueError(f"Unknown source type: {cfg.type}")


def _collection_exists(name: str) -> bool:
    """Check if collection exists on disk.

    Args:
        name (str): Name of the collection to check.

    Returns:
        bool: True if collection exists, False otherwise.
    """
    persister = DiskPersister(base_path="./data/collections")
    return persister.is_path_exists(name)


def _create_one(cfg: SourceConfig, use_cache: bool) -> None:
    """Create a single collection.

    Args:
        cfg (SourceConfig): Source configuration for the collection.
        use_cache (bool): Whether to enable on-disk read-cache decorator.
    """
    reader, converter = _build_reader_converter(cfg)

    creator = create_collection_creator(
        collection_name=cfg.name,
        indexers=[cfg.indexer],
        document_reader=reader,
        document_converter=converter,
        use_cache=use_cache,
    )
    creator.run()


def _update_one(cfg: SourceConfig) -> None:
    """Update a single collection.

    Args:
        cfg (SourceConfig): Source configuration for the collection to update.
    """
    updater = create_collection_updater(cfg.name)
    updater.run()


def create(
    configs: List[SourceConfig], *, use_cache: bool = True, force: bool = False
) -> None:
    """Create collections from source configurations.

    This function processes a list of source configurations and creates document
    collections for each one. It can optionally clear existing collections before
    creation and enable caching for improved performance.

    Args:
        configs (List[SourceConfig]): List of source configurations to process.
        use_cache (bool, optional): Enable on-disk read-cache decorator for improved
            performance on subsequent runs. Defaults to True.
        force (bool, optional): Delete existing collection folder first if it exists.
            Defaults to False.

    Raises:
        ValueError: If source configuration is invalid or required environment
            variables are missing.
    """
    for cfg in configs:
        if force and _collection_exists(cfg.name):
            clear([cfg.name])
        _create_one(cfg, use_cache)


def update(configs: List[SourceConfig]) -> None:
    """Update collections from source configurations.

    This function updates existing collections based on the provided source
    configurations. The collections must already exist.

    Args:
        configs (List[SourceConfig]): List of source configurations for collections
            to update.

    Raises:
        ValueError: If source configuration is invalid or collection doesn't exist.
    """
    for cfg in configs:
        _update_one(cfg)


def clear(collection_names: List[str]) -> None:
    """Clear (delete) collections by name.

    This function permanently removes collection folders and all their contents
    from disk. Use with caution as this operation cannot be undone.

    Args:
        collection_names (List[str]): List of collection names to delete.

    Warning:
        This operation permanently deletes collection data and cannot be undone.
    """
    persister = DiskPersister(base_path="./data/collections")
    for name in collection_names:
        persister.remove_folder(name)
