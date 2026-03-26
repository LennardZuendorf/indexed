"""Inspect service — collection status and metadata."""

from __future__ import annotations

from typing import Any, Optional

from .models import CollectionInfo, CollectionStatus


def status(
    names: Optional[list[str]] = None,
    collections_dir: Any = None,
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
    collections_dir: Any = None,
) -> CollectionInfo:
    """Get detailed info for a single collection.

    Args:
        name: Collection name.
        collections_dir: Override for collections directory.

    Returns:
        CollectionInfo with computed statistics.
    """
    from ..storage import get_collection_path, read_manifest

    manifest = read_manifest(name, collections_dir)
    col_path = get_collection_path(name, collections_dir)

    # Calculate disk size
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
