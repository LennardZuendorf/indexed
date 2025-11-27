"""Collection service for managing document collections.

This module provides functionality to create, update, and manage document collections
from various sources including Confluence, Jira, and local files. It handles the
orchestration of readers, converters, and persisters to build searchable collections.
"""

from typing import List, Any
from dataclasses import dataclass
from .models import SourceConfig, ProgressCallback
from utils.logger import setup_root_logger
from core.v1.engine.persisters.disk_persister import DiskPersister
from core.v1.engine.factories.create_collection_factory import create_collection_creator
from core.v1.engine.factories.update_collection_factory import create_collection_updater

setup_root_logger()


def _build_connector_from_config(cfg: SourceConfig, config_service: Any) -> Any:
    """Build connector using from_config() pattern.

    This function creates the appropriate connector based on the source configuration
    type using the new explicit registration pattern with ConfigService.

    Args:
        cfg (SourceConfig): Source configuration containing type, URL, query, and options.
        config_service: ConfigService instance from indexed_config

    Returns:
        BaseConnector: Connector instance with reader and converter properties.

    Raises:
        ValueError: If source type is unknown or configuration is invalid.
    """
    from connectors.jira import JiraConnector, JiraCloudConnector
    from connectors.confluence import ConfluenceConnector, ConfluenceCloudConnector
    from connectors.files import FileSystemConnector

    # Set config values from SourceConfig
    # Use unified namespaces (sources.jira for all Jira, sources.confluence for all Confluence)
    # The Cloud vs Server type is determined from the URL at runtime
    if cfg.type == "jira":
        config_service.set("sources.jira.url", cfg.base_url_or_path)
        config_service.set("sources.jira.query", cfg.query)
        # Pass reader_opts for auth credentials
        for key, value in cfg.reader_opts.items():
            config_service.set(f"sources.jira.{key}", value)
        return JiraConnector.from_config(config_service)

    elif cfg.type == "jiraCloud":
        # Use unified sources.jira namespace for Cloud as well
        config_service.set("sources.jira.url", cfg.base_url_or_path)
        config_service.set("sources.jira.query", cfg.query)
        # Pass reader_opts for auth credentials
        for key, value in cfg.reader_opts.items():
            config_service.set(f"sources.jira.{key}", value)
        return JiraCloudConnector.from_config(config_service)

    elif cfg.type == "confluence":
        config_service.set("sources.confluence.url", cfg.base_url_or_path)
        config_service.set("sources.confluence.query", cfg.query)
        # Pass reader_opts for auth credentials and options
        for key, value in cfg.reader_opts.items():
            config_service.set(f"sources.confluence.{key}", value)
        return ConfluenceConnector.from_config(config_service)

    elif cfg.type == "confluenceCloud":
        # Use unified sources.confluence namespace for Cloud as well
        config_service.set("sources.confluence.url", cfg.base_url_or_path)
        config_service.set("sources.confluence.query", cfg.query)
        # Pass reader_opts for auth credentials and options
        for key, value in cfg.reader_opts.items():
            config_service.set(f"sources.confluence.{key}", value)
        return ConfluenceCloudConnector.from_config(config_service)

    elif cfg.type == "localFiles":
        config_service.set("sources.files.path", cfg.base_url_or_path)
        if "includePatterns" in cfg.reader_opts:
            config_service.set("sources.files.include_patterns", cfg.reader_opts["includePatterns"])
        if "excludePatterns" in cfg.reader_opts:
            config_service.set("sources.files.exclude_patterns", cfg.reader_opts["excludePatterns"])
        if "failFast" in cfg.reader_opts:
            config_service.set("sources.files.fail_fast", cfg.reader_opts["failFast"])
        return FileSystemConnector.from_config(config_service)

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


def _create_one(
    cfg: SourceConfig,
    config_service: Any,
    use_cache: bool,
    progress_callback: ProgressCallback = None
) -> None:
    """Create a single collection.

    Args:
        cfg (SourceConfig): Source configuration for the collection.
        config_service: ConfigService instance from indexed_config
        use_cache (bool): Whether to enable on-disk read-cache decorator.
        progress_callback (ProgressCallback): Optional callback for progress updates.
    """
    connector = _build_connector_from_config(cfg, config_service)

    creator = create_collection_creator(
        collection_name=cfg.name,
        indexers=[cfg.indexer],
        document_reader=connector.reader,
        document_converter=connector.converter,
        use_cache=use_cache,
        progress_callback=progress_callback,
    )
    creator.run()


def _update_one(cfg: SourceConfig, progress_callback: ProgressCallback = None) -> None:
    """Update a single collection.

    Args:
        cfg (SourceConfig): Source configuration for the collection to update.
        progress_callback (ProgressCallback): Optional callback for progress updates.
    """
    updater = create_collection_updater(cfg.name, progress_callback)
    updater.run()


def create(
    configs: List[SourceConfig],
    *,
    config_service: Any = None,
    use_cache: bool = True,
    force: bool = False,
    progress_callback: ProgressCallback = None,
) -> None:
    """Create collections from source configurations.

    This function processes a list of source configurations and creates document
    collections for each one. It can optionally clear existing collections before
    creation and enable caching for improved performance.

    Args:
        configs (List[SourceConfig]): List of source configurations to process.
        config_service: ConfigService instance from indexed_config (creates new if None)
        use_cache (bool, optional): Enable on-disk read-cache decorator for improved
            performance on subsequent runs. Defaults to True.
        force (bool, optional): Delete existing collection folder first if it exists.
            Defaults to False.
        progress_callback (ProgressCallback, optional): Callback for progress updates.

    Raises:
        ValueError: If source configuration is invalid or required environment
            variables are missing.
    """
    if config_service is None:
        from indexed_config import ConfigService
        config_service = ConfigService()

    for cfg in configs:
        if force and _collection_exists(cfg.name):
            clear([cfg.name])
        _create_one(cfg, config_service, use_cache, progress_callback)


def update(
    configs: List[SourceConfig], progress_callback: ProgressCallback = None
) -> None:
    """Update collections from source configurations.

    This function updates existing collections based on the provided source
    configurations. The collections must already exist.

    Args:
        configs (List[SourceConfig]): List of source configurations for collections
            to update.
        progress_callback (ProgressCallback, optional): Callback for progress updates.

    Raises:
        ValueError: If source configuration is invalid or collection doesn't exist.
    """
    for cfg in configs:
        _update_one(cfg, progress_callback)


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


# DTOs for injected config
@dataclass
class CreateArgs:
    configs: List[SourceConfig]
    use_cache: bool = True
    force: bool = False


@dataclass
class UpdateArgs:
    configs: List[SourceConfig]
