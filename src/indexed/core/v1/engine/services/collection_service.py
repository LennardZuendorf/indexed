"""Collection service for managing document collections.

This module provides functionality to create, update, and manage document collections
from various sources including Confluence, Jira, and local files. It handles the
orchestration of readers, converters, and persisters to build searchable collections.
"""

from collections.abc import Callable
from typing import Any, List, Optional, Protocol, runtime_checkable

from indexed.protocols import BaseConnector

from .models import SourceConfig
from indexed.core.v1.engine.persisters.disk_persister import DiskPersister
from indexed.core.v1.engine.factories._types import ManifestFactory
from indexed.core.v1.engine.factories.create_collection_factory import (
    create_collection_creator,
)
from indexed.core.v1.config_models import (
    get_default_collections_path,
    get_default_caches_path,
)


@runtime_checkable
class _SupportsSaveState(Protocol):
    """Optional connector capability: not every source can persist change-tracking state."""

    def save_state(self, storage_path: str) -> None: ...


def _resolve_connector(
    cfg: SourceConfig,
    connector_factory: Callable[[SourceConfig], BaseConnector],
) -> BaseConnector:
    """Resolve connector from the required injected factory.

    ``composition`` is the single wiring site; the factory is always supplied,
    so there is no ``| None`` / runtime ``missing_wiring_error`` on this path.
    """
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


def collection_exists(name: str, collections_path: Optional[str] = None) -> bool:
    """Public raw on-disk existence check (present, independent of readability).

    ``InspectService`` OMITS collections whose manifest can't be read (a
    corrupt/missing manifest), so a corrupt-but-present collection never shows
    up in ``inspect()``/``status()``. CLI commands that need to distinguish
    "truly not found" from "present but corrupt" (``remove``, ``inspect``) use
    this instead of re-implementing the disk check (foundation/6 regression fix).
    """
    return _collection_exists(name, collections_path)


def _create_one(
    cfg: SourceConfig,
    use_cache: bool,
    phased_progress=None,
    collections_path: Optional[str] = None,
    caches_path: Optional[str] = None,
    *,
    connector_factory: Callable[[SourceConfig], BaseConnector],
    cache_decorator_factory: Callable[[Any, DiskPersister], Any] | None = None,
) -> None:
    """Create a single collection."""
    connector = _resolve_connector(cfg, connector_factory)

    creator = create_collection_creator(
        collection_name=cfg.name,
        indexers=[cfg.indexer],
        document_reader=connector.reader,
        document_converter=connector.converter,
        use_cache=use_cache,
        phased_progress=phased_progress,
        collections_path=collections_path,
        caches_path=caches_path,
        cache_decorator_factory=cache_decorator_factory,
    )
    creator.run()

    if isinstance(connector, _SupportsSaveState):
        resolved_path = collections_path or str(get_default_collections_path())
        persister = DiskPersister(base_path=resolved_path)
        connector.save_state(persister.get_full_path(cfg.name))


def _update_one(
    cfg: SourceConfig,
    phased_progress=None,
    collections_path: Optional[str] = None,
    *,
    manifest_factory: ManifestFactory,
) -> None:
    """Update a single collection."""
    # Lazy import: keeps collection_service off the factories -> core import cycle
    # that a module-load import of update_collection_factory would re-enter.
    from indexed.core.v1.engine.factories.update_collection_factory import (
        create_collection_updater,
    )

    updater = create_collection_updater(
        cfg.name,
        phased_progress=phased_progress,
        collections_path=collections_path,
        manifest_factory=manifest_factory,
    )
    updater.run()


def create(
    configs: List[SourceConfig],
    *,
    use_cache: bool = True,
    force: bool = False,
    phased_progress=None,
    collections_path: Optional[str] = None,
    caches_path: Optional[str] = None,
    connector_factory: Callable[[SourceConfig], BaseConnector],
    cache_decorator_factory: Callable[[Any, DiskPersister], Any] | None = None,
) -> None:
    """Create collections from source configurations."""
    resolved_collections = collections_path or str(get_default_collections_path())
    resolved_caches = caches_path or str(get_default_caches_path())

    if force:
        _clear_caches(resolved_caches)

    for cfg in configs:
        if force and _collection_exists(cfg.name, resolved_collections):
            clear([cfg.name], collections_path=resolved_collections)
        _create_one(
            cfg,
            use_cache,
            phased_progress=phased_progress,
            collections_path=resolved_collections,
            caches_path=resolved_caches,
            connector_factory=connector_factory,
            cache_decorator_factory=cache_decorator_factory,
        )


def update(
    configs: List[SourceConfig],
    phased_progress=None,
    collections_path: Optional[str] = None,
    *,
    manifest_factory: ManifestFactory,
) -> None:
    """Update collections from source configurations."""
    resolved_path = collections_path or str(get_default_collections_path())
    for cfg in configs:
        _update_one(
            cfg,
            phased_progress=phased_progress,
            collections_path=resolved_path,
            manifest_factory=manifest_factory,
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
