"""Collection creation pipeline — the v2 replacement for DocumentCollectionCreator.

Orchestrates: connector → adapter → embedding → VectorStoreIndex → persist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .adapter import PhasedProgress
from .errors import IngestionError


def create_collection(
    collection_name: str,
    connector: Any,
    *,
    embed_model_name: str = "all-MiniLM-L6-v2",
    store_type: str = "faiss",
    collections_dir: Optional[Path] = None,
    progress: Optional[PhasedProgress] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: int = 50,
    batch_size: Optional[int] = None,
    persistence_enabled: bool = True,
) -> dict[str, Any]:
    """Create a new collection by indexing documents from a connector.

    Args:
        collection_name: Unique name for the collection.
        connector: BaseConnector instance with ``reader`` and ``converter``.
        embed_model_name: HuggingFace model name for embeddings.
        store_type: Vector store backend (default ``"faiss"``).
        collections_dir: Override for the collections directory.
        progress: Optional phased progress callback.
        chunk_size: If set, re-split adapter nodes with a LlamaIndex
            ``SentenceSplitter`` of this token size. ``None`` keeps the
            connector's own chunking unchanged (backward compatible).
        chunk_overlap: Token overlap used when ``chunk_size`` is set.
        batch_size: Embedding batch size. ``None`` keeps the model default.
        persistence_enabled: If False, build the index but skip the disk
            write (and manifest). Useful for dry runs / tests.

    Returns:
        The manifest dict.

    Raises:
        IngestionError: If no documents are found or indexing fails.
    """
    from llama_index.core import VectorStoreIndex

    from .adapter import connector_to_nodes
    from .embedding import get_embed_model
    from .storage import (
        create_storage_context,
        persist_collection,
        remove_collection,
        write_manifest,
    )
    from .vector_store import create_vector_store

    # Step 1: Convert connector output to nodes. The existing collection (if
    # any) is intentionally NOT removed yet — a failed build must leave the
    # prior collection intact. We only swap it out after a successful build.
    nodes = connector_to_nodes(
        connector.reader,
        connector.converter,
        collection_name,
        progress=progress,
    )

    if not nodes:
        raise IngestionError(f"No documents found for collection '{collection_name}'.")

    # Step 2: Optionally re-chunk nodes via a node parser when chunk settings
    # are supplied. Connectors already chunk, so this only takes effect when a
    # caller explicitly configures chunk_size.
    if chunk_size is not None:
        nodes = _split_nodes(nodes, chunk_size, chunk_overlap)

    # Step 3: Set up embedding model
    if progress:
        progress.start_phase("Generating embeddings", total=len(nodes))

    embed_model = get_embed_model(embed_model_name)
    if batch_size is not None:
        embed_model.embed_batch_size = batch_size

    # Step 4: Create vector store + storage context
    embed_dim = _get_embed_dim(embed_model)
    vector_store = create_vector_store(store_type, embed_dim)
    storage_context = create_storage_context(vector_store)

    # Step 5: Build index (LlamaIndex handles embedding + FAISS insertion)
    try:
        VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            embed_model=embed_model,
            show_progress=False,
        )
    except Exception as exc:
        msg = f"Failed to build index for '{collection_name}': {exc}"
        raise IngestionError(msg) from exc

    if progress:
        progress.finish_phase("Generating embeddings")

    # Step 6: Build succeeded — now it is safe to replace any prior collection.
    unique_docs = {n.metadata.get("source_id", n.id_) for n in nodes}
    source_type = getattr(connector, "connector_type", "")

    if not persistence_enabled:
        # Skip the disk write entirely; return an in-memory manifest so the
        # return shape stays consistent for callers.
        return _build_manifest(
            collection_name,
            num_documents=len(unique_docs),
            num_chunks=len(nodes),
            source_type=source_type,
            embed_model_name=embed_model_name,
            store_type=store_type,
        )

    if progress:
        progress.start_phase("Writing to disk")

    # Replace-on-success: remove the old collection only now that the new
    # index has been built without error.
    remove_collection(collection_name, collections_dir)

    persist_collection(storage_context, collection_name, collections_dir)

    manifest = write_manifest(
        collection_name,
        num_documents=len(unique_docs),
        num_chunks=len(nodes),
        source_type=source_type,
        embed_model_name=embed_model_name,
        vector_store_type=store_type,
        collections_dir=collections_dir,
    )

    if progress:
        progress.finish_phase("Writing to disk")

    return manifest


def _split_nodes(nodes: list, chunk_size: int, chunk_overlap: int) -> list:
    """Re-split adapter nodes with a SentenceSplitter, preserving metadata."""
    from llama_index.core.node_parser import SentenceSplitter

    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return splitter.get_nodes_from_documents(nodes)


def _build_manifest(
    collection_name: str,
    *,
    num_documents: int,
    num_chunks: int,
    source_type: str,
    embed_model_name: str,
    store_type: str,
) -> dict[str, Any]:
    """Build a manifest dict without writing it to disk."""
    from datetime import datetime, timezone

    now = datetime.now(tz=timezone.utc).isoformat()
    return {
        "name": collection_name,
        "version": "2.0",
        "source_type": source_type,
        "num_documents": num_documents,
        "num_chunks": num_chunks,
        "embed_model_name": embed_model_name,
        "vector_store_type": store_type,
        "created_time": now,
        "updated_time": now,
    }


# Known dimensions for common models — avoids a test embedding call.
_KNOWN_DIMS: dict[str, int] = {
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
    "multi-qa-distilbert-cos-v1": 768,
}


def _get_embed_dim(embed_model: Any) -> int:
    """Get the embedding dimension, preferring known values."""
    model_name = getattr(embed_model, "model_name", "")
    # Strip the sentence-transformers/ prefix if present
    short_name = model_name.rsplit("/", 1)[-1] if "/" in model_name else model_name
    if short_name in _KNOWN_DIMS:
        return _KNOWN_DIMS[short_name]
    # Fallback: embed a short string to discover dimension
    return len(embed_model.get_query_embedding("dimension probe"))
