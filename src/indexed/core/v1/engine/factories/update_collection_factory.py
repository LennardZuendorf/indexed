"""Factory for creating collection updaters.

This module creates DocumentCollectionCreator instances configured for
update operations. It reads the collection manifest and reconstructs the
connector's reader/converter via a single injected ``manifest_factory`` — one
path for every source, no per-connector-type branches (the connector owns its
manifest logic in ``from_manifest``).
"""

import json

from pydantic import ValidationError

from indexed.core.v1.config_models import get_default_collections_path
from indexed.core.v1.engine.core.documents_collection_creator import (
    OPERATION_TYPE,
    DocumentCollectionCreator,
)
from indexed.core.v1.engine.factories._types import ManifestFactory
from indexed.core.v1.engine.indexes.indexer_factory import load_indexer
from indexed.core.v1.engine.persisters.disk_persister import DiskPersister
from indexed.protocols import Manifest
from indexed.utils.performance import log_execution_duration


def create_collection_updater(
    collection_name: str,
    phased_progress=None,
    collections_path: str | None = None,
    *,
    manifest_factory: ManifestFactory,
):
    """Create a collection updater for incremental updates.

    Args:
        collection_name: Name of the collection to update
        phased_progress: Optional PhasedProgressCallback for multi-stage display.
        collections_path: Optional path for collections storage.
                         Defaults to resolved path from storage config.
        manifest_factory: Required — rebuilds (reader, converter, deletions,
                          post_run) for the collection's stored manifest.

    Returns:
        DocumentCollectionCreator configured for UPDATE operation
    """
    return log_execution_duration(
        lambda: _create_collection_updater(
            collection_name,
            phased_progress,
            collections_path,
            manifest_factory,
        ),
        identifier="Preparing collection updater",
    )


def _create_collection_updater(
    collection_name: str,
    phased_progress,
    collections_path: str | None,
    manifest_factory: ManifestFactory,
):
    """Internal implementation of collection updater creation."""
    resolved_path = collections_path or str(get_default_collections_path())
    disk_persister = DiskPersister(base_path=resolved_path)

    if not disk_persister.is_path_exists(collection_name):
        raise ValueError(f"Collection {collection_name} does not exist")

    # A partial/legacy/corrupt manifest raises a raw pydantic ValidationError or
    # JSON error — neither an IndexedError — so surface a clean, mapped message
    # (matching the "does not exist" ValueError precedent above) instead of
    # letting an internal traceback reach the CLI.
    try:
        manifest = Manifest.from_disk(
            json.loads(
                disk_persister.read_text_file(f"{collection_name}/manifest.json")
            )
        )
    except (ValidationError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Collection '{collection_name}' has an invalid or corrupt manifest: {exc}"
        ) from exc

    # Source-agnostic: the connector rebuilds itself from its own manifest.
    run = manifest_factory(manifest, disk_persister.get_full_path(collection_name))

    document_indexers = [
        load_indexer(indexer.name, collection_name, disk_persister)
        for indexer in manifest.indexers
    ]

    # The connector's optional post_run hook (persists ChangeTracker state) is
    # threaded straight into the creator, whose run() invokes it after a
    # successful update — no wrapper needed.
    return DocumentCollectionCreator(
        collection_name=collection_name,
        document_reader=run.reader,
        document_converter=run.converter,
        document_indexers=document_indexers,
        persister=disk_persister,
        operation_type=OPERATION_TYPE.UPDATE,
        phased_progress=phased_progress,
        explicit_deletions=run.deletions,
        post_run=run.post_run,
    )
