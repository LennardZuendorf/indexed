"""Collection persistence via LlamaIndex StorageContext.

Handles creating, loading, persisting, and removing collections on disk.
Each collection is stored in its own directory under the collections root.
A ``manifest.json`` file alongside LlamaIndex's persistence files stores
metadata that LlamaIndex doesn't track (source type, timestamps, counts).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .errors import CollectionNotFoundError, VectorStoreError

if TYPE_CHECKING:
    from llama_index.core import StorageContext


def get_collections_dir() -> Path:
    """Return the default collections directory from config or fallback."""
    try:
        from core.v1.config_models import get_default_collections_path

        return get_default_collections_path()
    except ImportError:
        return Path.home() / ".indexed" / "data" / "collections"


def get_collection_path(
    collection_name: str,
    collections_dir: Optional[Path] = None,
) -> Path:
    """Resolve the on-disk path for a collection."""
    base = collections_dir or get_collections_dir()
    return base / collection_name


def create_storage_context(
    vector_store: Any,
) -> "StorageContext":
    """Create a new StorageContext with the given vector store."""
    from llama_index.core import StorageContext

    return StorageContext.from_defaults(vector_store=vector_store)


def load_storage_context(
    collection_name: str,
    collections_dir: Optional[Path] = None,
) -> "StorageContext":
    """Load a persisted StorageContext from disk.

    Raises:
        CollectionNotFoundError: If the collection directory doesn't exist.
        VectorStoreError: If loading fails.
    """
    persist_dir = get_collection_path(collection_name, collections_dir)
    if not persist_dir.exists():
        raise CollectionNotFoundError(collection_name)

    try:
        from llama_index.core import StorageContext
        from llama_index.vector_stores.faiss import FaissVectorStore

        vector_store = FaissVectorStore.from_persist_dir(str(persist_dir))
        return StorageContext.from_defaults(
            vector_store=vector_store,
            persist_dir=str(persist_dir),
        )
    except Exception as exc:
        msg = f"Failed to load collection '{collection_name}': {exc}"
        raise VectorStoreError(msg) from exc


def persist_collection(
    storage_context: "StorageContext",
    collection_name: str,
    collections_dir: Optional[Path] = None,
) -> Path:
    """Persist a StorageContext to disk.

    Returns:
        The collection directory path.
    """
    persist_dir = get_collection_path(collection_name, collections_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    storage_context.persist(persist_dir=str(persist_dir))
    return persist_dir


def write_manifest(
    collection_name: str,
    *,
    num_documents: int,
    num_chunks: int,
    source_type: str = "",
    embed_model_name: str = "all-MiniLM-L6-v2",
    vector_store_type: str = "faiss",
    collections_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Write a manifest.json file with collection metadata.

    This supplements LlamaIndex's persistence with metadata it doesn't track.
    """
    now = datetime.now(tz=timezone.utc).isoformat()
    manifest: dict[str, Any] = {
        "name": collection_name,
        "version": "2.0",
        "source_type": source_type,
        "num_documents": num_documents,
        "num_chunks": num_chunks,
        "embed_model_name": embed_model_name,
        "vector_store_type": vector_store_type,
        "created_time": now,
        "updated_time": now,
    }

    manifest_path = (
        get_collection_path(collection_name, collections_dir) / "manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return manifest


def read_manifest(
    collection_name: str,
    collections_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Read a collection's manifest.json.

    Raises:
        CollectionNotFoundError: If the manifest doesn't exist.
    """
    manifest_path = (
        get_collection_path(collection_name, collections_dir) / "manifest.json"
    )
    if not manifest_path.exists():
        raise CollectionNotFoundError(collection_name)

    return json.loads(manifest_path.read_text())


def remove_collection(
    collection_name: str,
    collections_dir: Optional[Path] = None,
) -> bool:
    """Delete a collection directory from disk.

    Returns:
        True if the collection existed and was removed, False if it didn't exist.
    """
    path = get_collection_path(collection_name, collections_dir)
    if path.exists():
        shutil.rmtree(path)
        return True
    return False


def list_collection_names(
    collections_dir: Optional[Path] = None,
) -> list[str]:
    """List all collection names that have a manifest.json."""
    base = collections_dir or get_collections_dir()
    if not base.exists():
        return []

    return sorted(
        d.name for d in base.iterdir() if d.is_dir() and (d / "manifest.json").exists()
    )
