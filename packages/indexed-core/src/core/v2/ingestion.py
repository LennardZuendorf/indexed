"""Collection creation pipeline — the v2 replacement for DocumentCollectionCreator.

Orchestrates: connector → adapter → embedding → VectorStoreIndex → persist.
"""

from __future__ import annotations

from typing import Any, Optional

from .adapter import PhasedProgress
from .errors import IngestionError


def create_collection(
    collection_name: str,
    connector: Any,
    *,
    embed_model_name: str = "all-MiniLM-L6-v2",
    store_type: str = "faiss",
    collections_dir: Any = None,
    progress: Optional[PhasedProgress] = None,
) -> dict[str, Any]:
    """Create a new collection by indexing documents from a connector.

    Flow:
        1. Remove existing collection if present
        2. Convert connector output to LlamaIndex TextNodes via adapter
        3. Create embedding model
        4. Create vector store + StorageContext
        5. Build VectorStoreIndex (LlamaIndex embeds + indexes)
        6. Persist to disk
        7. Write manifest

    Args:
        collection_name: Unique name for the collection.
        connector: BaseConnector instance with ``reader`` and ``converter``.
        embed_model_name: HuggingFace model name for embeddings.
        store_type: Vector store backend (default ``"faiss"``).
        collections_dir: Override for the collections directory.
        progress: Optional phased progress callback.

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

    # Step 1: Clean slate
    remove_collection(collection_name, collections_dir)

    # Step 2: Convert connector output to nodes
    nodes = connector_to_nodes(
        connector.reader,
        connector.converter,
        collection_name,
        progress=progress,
    )

    if not nodes:
        raise IngestionError(f"No documents found for collection '{collection_name}'.")

    # Step 3: Set up embedding model
    if progress:
        progress.start_phase("Generating embeddings", total=len(nodes))

    embed_model = get_embed_model(embed_model_name)

    # Step 4: Create vector store + storage context
    embed_dim = len(embed_model.get_query_embedding("test"))
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

    # Step 6: Persist
    if progress:
        progress.start_phase("Writing to disk")

    persist_collection(storage_context, collection_name, collections_dir)

    # Step 7: Write manifest
    # Count unique source documents from node metadata
    unique_docs = {n.metadata.get("source_id", n.id_) for n in nodes}
    source_type = getattr(connector, "connector_type", "")

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
