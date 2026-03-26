"""Search service — stateful and stateless search interfaces."""

from __future__ import annotations

from typing import Any, Optional

from .models import SourceConfig


class SearchService:
    """Stateful search service with index caching.

    Good for long-running processes (MCP servers) where loading the
    index once and reusing it across queries improves latency.
    """

    def __init__(
        self,
        embed_model_name: str = "all-MiniLM-L6-v2",
        collections_dir: Any = None,
    ) -> None:
        self._embed_model_name = embed_model_name
        self._collections_dir = collections_dir

    def search(
        self,
        query: str,
        *,
        collection_name: Optional[str] = None,
        similarity_top_k: int = 30,
        max_docs: int = 10,
        include_matched_chunks: bool = True,
    ) -> dict[str, Any]:
        """Search a specific collection or all collections."""
        from ..retrieval import search_collection
        from ..storage import list_collection_names

        if collection_name:
            return search_collection(
                query,
                collection_name,
                similarity_top_k=similarity_top_k,
                embed_model_name=self._embed_model_name,
                max_docs=max_docs,
                include_matched_chunks=include_matched_chunks,
                collections_dir=self._collections_dir,
            )

        # Search all collections and merge results
        names = list_collection_names(self._collections_dir)
        all_results: list[dict[str, Any]] = []
        for name in names:
            result = search_collection(
                query,
                name,
                similarity_top_k=similarity_top_k,
                embed_model_name=self._embed_model_name,
                max_docs=max_docs,
                include_matched_chunks=include_matched_chunks,
                collections_dir=self._collections_dir,
            )
            all_results.append(result)

        return {
            "query": query,
            "collections": all_results,
        }


def search(
    query: str,
    *,
    configs: Optional[list[SourceConfig]] = None,
    max_docs: int = 10,
    max_chunks: int = 30,
    include_matched_chunks: bool = True,
    embed_model_name: str = "all-MiniLM-L6-v2",
    collections_dir: Any = None,
) -> dict[str, Any]:
    """Stateless search function — convenience wrapper for CLI usage.

    Args:
        query: Search query text.
        configs: Optional list of SourceConfig to search specific collections.
            If None, auto-discovers all collections.
        max_docs: Maximum documents per collection.
        max_chunks: Top-k for the retriever.
        include_matched_chunks: Include chunk text in results.
        embed_model_name: Embedding model name.
        collections_dir: Override for collections directory.
    """
    from ..retrieval import search_collection
    from ..storage import list_collection_names

    if configs:
        names = [c.name for c in configs]
    else:
        names = list_collection_names(collections_dir)

    all_results: list[dict[str, Any]] = []
    for name in names:
        result = search_collection(
            query,
            name,
            similarity_top_k=max_chunks,
            embed_model_name=embed_model_name,
            max_docs=max_docs,
            include_matched_chunks=include_matched_chunks,
            collections_dir=collections_dir,
        )
        all_results.append(result)

    if len(all_results) == 1:
        return all_results[0]

    return {
        "query": query,
        "collections": all_results,
    }
