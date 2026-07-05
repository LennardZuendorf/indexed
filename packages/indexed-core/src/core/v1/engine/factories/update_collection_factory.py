"""Factory for creating collection updaters.

This module creates DocumentCollectionCreator instances configured for
update operations. It reads the collection manifest to reconstruct
the connector and applies date filters for incremental updates.

Uses the same from_config() pattern as create operations for unified
config handling across the CLI.
"""

from collections.abc import Callable
import json
from typing import Any

from indexed_config.errors import missing_wiring_error

from core.v1.engine.factories._types import (
    LocalFilesUpdateFactory,
    ManifestConnectorFactory,
)
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
    manifest_connector_factory: ManifestConnectorFactory | None = None,
    local_files_update_factory: LocalFilesUpdateFactory | None = None,
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
    manifest_connector_factory: ManifestConnectorFactory | None = None,
    local_files_update_factory: LocalFilesUpdateFactory | None = None,
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
            raise missing_wiring_error("local_files_update_factory")
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


def _create_reader_and_converter(
    manifest: dict,
    manifest_connector_factory: ManifestConnectorFactory | None = None,
) -> tuple[Any, Any]:
    """Create reader and converter from manifest via injected factory."""
    if manifest_connector_factory is None:
        raise missing_wiring_error("manifest_connector_factory")
    return manifest_connector_factory(manifest)
