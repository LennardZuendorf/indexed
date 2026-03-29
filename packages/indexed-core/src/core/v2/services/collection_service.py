"""Collection management service — create, update, clear collections."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .models import PhasedProgressCallback


def create(
    name: str,
    connector: Any,
    *,
    embed_model_name: str = "all-MiniLM-L6-v2",
    store_type: str = "faiss",
    collections_dir: Optional[Path] = None,
    progress: Optional[PhasedProgressCallback] = None,
) -> dict[str, Any]:
    """Create a new collection from a connector.

    Delegates to :func:`core.v2.ingestion.create_collection`.
    """
    from ..ingestion import create_collection

    return create_collection(
        name,
        connector,
        embed_model_name=embed_model_name,
        store_type=store_type,
        collections_dir=collections_dir,
        progress=progress,
    )


def update(
    name: str,
    connector: Any,
    *,
    embed_model_name: str = "all-MiniLM-L6-v2",
    store_type: str = "faiss",
    collections_dir: Optional[Path] = None,
    progress: Optional[PhasedProgressCallback] = None,
) -> dict[str, Any]:
    """Update a collection by re-indexing from the connector.

    V2 does not support incremental updates yet — this removes the
    existing collection and recreates it from scratch.
    """
    return create(
        name,
        connector,
        embed_model_name=embed_model_name,
        store_type=store_type,
        collections_dir=collections_dir,
        progress=progress,
    )


def clear(
    names: list[str],
    collections_dir: Optional[Path] = None,
) -> list[str]:
    """Remove one or more collections from disk.

    Returns:
        List of collection names that were actually removed.
    """
    from ..storage import remove_collection

    return [name for name in names if remove_collection(name, collections_dir)]
