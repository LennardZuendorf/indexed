"""Search/retrieval pipeline — the v2 replacement for DocumentCollectionSearcher.

Loads a persisted collection and queries it via LlamaIndex's VectorIndexRetriever.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def search_collection(
    query: str,
    collection_name: str,
    *,
    similarity_top_k: int = 30,
    embed_model_name: str = "all-MiniLM-L6-v2",
    max_docs: int = 10,
    include_matched_chunks: bool = True,
    collections_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Search a single collection using LlamaIndex retriever.

    Args:
        query: Search query text.
        collection_name: Name of the collection to search.
        similarity_top_k: Number of similar chunks to retrieve.
        embed_model_name: Model to use for query embedding.
        max_docs: Maximum documents in the result.
        include_matched_chunks: Whether to include chunk text in results.
        collections_dir: Override for the collections directory.

    Returns:
        Dict with ``collectionName`` and ``results`` keys.
    """
    from llama_index.core import VectorStoreIndex

    from .embedding import get_embed_model
    from .storage import load_storage_context

    embed_model = get_embed_model(embed_model_name)

    storage_context = load_storage_context(collection_name, collections_dir)
    index = VectorStoreIndex.from_storage_context(
        storage_context, embed_model=embed_model
    )

    retriever = index.as_retriever(similarity_top_k=similarity_top_k)
    retrieved_nodes = retriever.retrieve(query)

    return _format_results(
        collection_name, retrieved_nodes, max_docs, include_matched_chunks
    )


def _format_results(
    collection_name: str,
    retrieved_nodes: list,
    max_docs: int,
    include_matched_chunks: bool,
) -> dict[str, Any]:
    """Convert LlamaIndex NodeWithScore results to v1-compatible format.

    Groups results by source document, keeping the best score per chunk.
    """
    doc_results: dict[str, dict[str, Any]] = {}

    for node_with_score in retrieved_nodes:
        node = node_with_score.node
        score = node_with_score.score
        source_id = node.metadata.get("source_id", node.node_id)

        if source_id not in doc_results:
            doc_results[source_id] = {
                "id": source_id,
                "url": node.metadata.get("url", ""),
                "path": node.metadata.get("url", ""),
                "matchedChunks": [],
            }

        chunk_entry: dict[str, Any] = {
            "chunkNumber": node.metadata.get("chunk_index", 0),
            "score": float(score) if score is not None else 0.0,
        }
        if include_matched_chunks:
            chunk_entry["content"] = {"indexedData": node.text}

        doc_results[source_id]["matchedChunks"].append(chunk_entry)

    results = list(doc_results.values())[:max_docs]

    return {
        "collectionName": collection_name,
        "results": results,
    }
