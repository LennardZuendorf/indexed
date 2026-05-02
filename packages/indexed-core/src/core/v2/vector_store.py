"""Pluggable vector store factory for LlamaIndex.

Creates LlamaIndex-compatible vector stores. FAISS is the default backend.
New backends can be added by extending :func:`create_vector_store`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import VectorStoreError

if TYPE_CHECKING:
    from llama_index.core.vector_stores.types import BasePydanticVectorStore


def create_vector_store(
    store_type: str = "faiss",
    embed_dim: int = 384,
) -> "BasePydanticVectorStore":
    """Create a LlamaIndex vector store instance.

    Args:
        store_type: Backend type. Currently only ``"faiss"`` is supported.
        embed_dim: Embedding dimension for index creation.

    Returns:
        A LlamaIndex vector store ready for use with ``StorageContext``.

    Raises:
        VectorStoreError: If the store type is unknown or creation fails.
    """
    if store_type == "faiss":
        return _create_faiss_store(embed_dim)

    msg = f"Unknown vector store type: '{store_type}'. Supported types: faiss"
    raise VectorStoreError(msg)


def _create_faiss_store(
    embed_dim: int,
) -> "BasePydanticVectorStore":
    """Create a FAISS vector store with IndexFlatL2."""
    try:
        import faiss
        from llama_index.vector_stores.faiss import FaissVectorStore
    except ImportError as exc:
        msg = (
            "faiss-cpu and llama-index-vector-stores-faiss are required. "
            "Install with: uv add faiss-cpu llama-index-vector-stores-faiss"
        )
        raise VectorStoreError(msg) from exc

    faiss_index = faiss.IndexFlatL2(embed_dim)
    return FaissVectorStore(faiss_index=faiss_index)
