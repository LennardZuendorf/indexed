"""Inspect service — collection status and metadata."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .models import CollectionInfo, CollectionStatus

logger = logging.getLogger(__name__)


def status(
    names: Optional[list[str]] = None,
    collections_dir: Optional[Path] = None,
) -> list[CollectionStatus]:
    """Get status for one or more collections.

    Args:
        names: Collection names to inspect. If None, inspects all.
        collections_dir: Override for collections directory.

    Returns:
        List of CollectionStatus objects.
    """
    from ..storage import list_collection_names, read_manifest

    if names is None:
        names = list_collection_names(collections_dir)

    results: list[CollectionStatus] = []
    for name in names:
        try:
            manifest = read_manifest(name, collections_dir)
        except Exception:
            logger.debug("Skipping collection '%s': manifest unreadable", name)
            continue

        results.append(
            CollectionStatus(
                name=manifest.get("name", name),
                number_of_documents=manifest.get("num_documents", 0),
                number_of_chunks=manifest.get("num_chunks", 0),
                updated_time=manifest.get("updated_time", ""),
                last_modified_document_time=manifest.get("updated_time", ""),
                indexers=[manifest.get("embed_model_name", "")],
                source_type=manifest.get("source_type", ""),
            )
        )

    return results


def inspect(
    name: str,
    collections_dir: Optional[Path] = None,
) -> CollectionInfo:
    """Get detailed info for a single collection.

    Raises:
        CollectionNotFoundError: If the collection has no manifest.
        CollectionEngineMismatchError: If the manifest is not a v2 manifest
            (e.g. a v1 collection inspected under a forced ``--engine v2``).
            Surfacing this prevents the hollow "Unknown / 0 docs / 0 chunks"
            card that silently appears when v2 keys are read off a v1 manifest.
    """
    from ..errors import CollectionEngineMismatchError
    from ..storage import get_collection_path, read_manifest

    manifest = read_manifest(name, collections_dir)
    version = manifest.get("version")
    if not (isinstance(version, str) and version.startswith("2")):
        raise CollectionEngineMismatchError(name, "v1")
    col_path = get_collection_path(name, collections_dir)

    disk_size = sum(f.stat().st_size for f in col_path.rglob("*") if f.is_file())

    return CollectionInfo(
        name=manifest.get("name", name),
        source_type=manifest.get("source_type", ""),
        number_of_documents=manifest.get("num_documents", 0),
        number_of_chunks=manifest.get("num_chunks", 0),
        disk_size_bytes=disk_size,
        created_time=manifest.get("created_time", ""),
        updated_time=manifest.get("updated_time", ""),
        indexers=[manifest.get("embed_model_name", "")],
    )
