"""Collection service for managing document collections.

This module provides functionality to create, update, and manage document collections
from various sources including Confluence, Jira, and local files. It handles the
orchestration of readers, converters, and persisters to build searchable collections.
"""

from collections.abc import Callable
from typing import Any, List, Optional
from dataclasses import dataclass

from indexed_config.errors import ConfigurationError

from .models import SourceConfig, ProgressCallback
from utils.logger import setup_root_logger
from core.v1.engine.persisters.disk_persister import DiskPersister
from core.v1.engine.factories.create_collection_factory import create_collection_creator
from core.v1.config_models import get_default_collections_path, get_default_caches_path

# NOTE: update_collection_factory is imported lazily in _update_one() to avoid
# circular import: connectors -> core.v1 -> collection_service -> update_collection_factory -> connectors

setup_root_logger()


def _build_connector_from_config(
    cfg: SourceConfig,
    config_service: Any,
    connector_factory: Callable[[SourceConfig], Any] | None = None,
) -> Any:
    """Build connector via injected factory (app composition root owns wiring)."""
    if connector_factory is None:
        raise ConfigurationError(
            "connector_factory must be injected by the app layer; "
            "see indexed.bootstrap.build_connector"
        )
    return connector_factory(cfg)


def _clear_caches(caches_path: str) -> None:
    """Remove all read-cache entries so stale data doesn't persist."""
    import os
    import shutil

    from loguru import logger

    if not os.path.isdir(caches_path):
        return
    for entry in os.listdir(caches_path):
        entry_path = os.path.join(caches_path, entry)
        try:
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path, ignore_errors=True)
            else:
                os.remove(entry_path)
        except OSError as exc:
            logger.warning("Could not remove cache entry %s: %s", entry_path, exc)


def _collection_exists(name: str, collections_path: Optional[str] = None) -> bool:
    """Check if collection exists on disk.

    Args:
        name (str): Name of the collection to check.
        collections_path: Optional path for collections storage.

    Returns:
        bool: True if collection exists, False otherwise.
    """
    resolved_path = collections_path or str(get_default_collections_path())
    persister = DiskPersister(base_path=resolved_path)
    return persister.is_path_exists(name)


def _create_one(
    cfg: SourceConfig,
    config_service: Any,
    use_cache: bool,
    progress_callback: ProgressCallback = None,
    phased_progress=None,
    collections_path: Optional[str] = None,
    caches_path: Optional[str] = None,
    connector_factory: Callable[[SourceConfig], Any] | None = None,
    cache_decorator_factory: Callable[[Any, DiskPersister], Any] | None = None,
) -> None:
    """Create a single collection."""
    connector = _build_connector_from_config(cfg, config_service, connector_factory)

    creator = create_collection_creator(
        collection_name=cfg.name,
        indexers=[cfg.indexer],
        document_reader=connector.reader,
        document_converter=connector.converter,
        use_cache=use_cache,
        progress_callback=progress_callback,
        phased_progress=phased_progress,
        collections_path=collections_path,
        caches_path=caches_path,
        cache_decorator_factory=cache_decorator_factory,
    )
    creator.run()

    if hasattr(connector, "save_state"):
        resolved_path = collections_path or str(get_default_collections_path())
        persister = DiskPersister(base_path=resolved_path)
        connector.save_state(persister.get_full_path(cfg.name))


def _update_one(
    cfg: SourceConfig,
    progress_callback: ProgressCallback = None,
    phased_progress=None,
    collections_path: Optional[str] = None,
    manifest_connector_factory: Callable[[dict], tuple[Any, Any]] | None = None,
    local_files_update_factory: Callable[
        [dict, str, DiskPersister],
        tuple[Any, Any, list[str], Callable[[], None] | None],
    ]
    | None = None,
) -> None:
    """Update a single collection."""
    from core.v1.engine.factories.update_collection_factory import (
        create_collection_updater,
    )

    updater = create_collection_updater(
        cfg.name,
        progress_callback,
        phased_progress=phased_progress,
        collections_path=collections_path,
        manifest_connector_factory=manifest_connector_factory,
        local_files_update_factory=local_files_update_factory,
    )
    updater.run()


def create(
    configs: List[SourceConfig],
    *,
    config_service: Any = None,
    use_cache: bool = True,
    force: bool = False,
    progress_callback: ProgressCallback = None,
    phased_progress=None,
    collections_path: Optional[str] = None,
    caches_path: Optional[str] = None,
    connector_factory: Callable[[SourceConfig], Any] | None = None,
    cache_decorator_factory: Callable[[Any, DiskPersister], Any] | None = None,
) -> None:
    """Create collections from source configurations."""
    if config_service is None:
        from indexed_config import ConfigService

        config_service = ConfigService()

    resolved_collections = collections_path or str(get_default_collections_path())
    resolved_caches = caches_path or str(get_default_caches_path())

    if force:
        _clear_caches(resolved_caches)

    for cfg in configs:
        if force and _collection_exists(cfg.name, resolved_collections):
            clear([cfg.name], collections_path=resolved_collections)
        _create_one(
            cfg,
            config_service,
            use_cache,
            progress_callback,
            phased_progress=phased_progress,
            collections_path=resolved_collections,
            caches_path=resolved_caches,
            connector_factory=connector_factory,
            cache_decorator_factory=cache_decorator_factory,
        )


def update(
    configs: List[SourceConfig],
    progress_callback: ProgressCallback = None,
    phased_progress=None,
    collections_path: Optional[str] = None,
    manifest_connector_factory: Callable[[dict], tuple[Any, Any]] | None = None,
    local_files_update_factory: Callable[
        [dict, str, DiskPersister],
        tuple[Any, Any, list[str], Callable[[], None] | None],
    ]
    | None = None,
) -> None:
    """Update collections from source configurations."""
    resolved_path = collections_path or str(get_default_collections_path())
    for cfg in configs:
        _update_one(
            cfg,
            progress_callback,
            phased_progress=phased_progress,
            collections_path=resolved_path,
            manifest_connector_factory=manifest_connector_factory,
            local_files_update_factory=local_files_update_factory,
        )


def clear(
    collection_names: List[str],
    collections_path: Optional[str] = None,
) -> None:
    """Clear (delete) collections by name."""
    resolved_path = collections_path or str(get_default_collections_path())
    persister = DiskPersister(base_path=resolved_path)
    for name in collection_names:
        persister.remove_folder(name)


@dataclass
class CreateArgs:
    configs: List[SourceConfig]
    use_cache: bool = True
    force: bool = False


@dataclass
class UpdateArgs:
    configs: List[SourceConfig]
