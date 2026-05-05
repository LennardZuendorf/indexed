"""Search service — stateful and stateless search interfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .models import SourceConfig


def _search_collections(
    query: str,
    names: list[str],
    *,
    similarity_top_k: int = 30,
    embed_model_name: str = "all-MiniLM-L6-v2",
    max_docs: int = 10,
    include_matched_chunks: bool = True,
    collections_dir: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Search multiple collections and return raw results."""
    from ..retrieval import search_collection

    return [
        search_collection(
            query,
            name,
            similarity_top_k=similarity_top_k,
            embed_model_name=embed_model_name,
            max_docs=max_docs,
            include_matched_chunks=include_matched_chunks,
            collections_dir=collections_dir,
        )
        for name in names
    ]


class SearchService:
    """Stateful search service.

    Good for long-running processes (MCP servers) where configuration
    is set once and reused across queries.
    """

    def __init__(
        self,
        embed_model_name: str = "all-MiniLM-L6-v2",
        collections_dir: Optional[Path] = None,
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
        from ..storage import list_collection_names

        if collection_name:
            names = [collection_name]
        else:
            names = list_collection_names(self._collections_dir)

        results = _search_collections(
            query,
            names,
            similarity_top_k=similarity_top_k,
            embed_model_name=self._embed_model_name,
            max_docs=max_docs,
            include_matched_chunks=include_matched_chunks,
            collections_dir=self._collections_dir,
        )

        if len(results) == 1:
            return results[0]

        return {"query": query, "collections": results}


def search(
    query: str,
    *,
    configs: Optional[list[SourceConfig]] = None,
    max_docs: int = 10,
    max_chunks: int = 30,
    include_matched_chunks: bool = True,
    embed_model_name: str = "all-MiniLM-L6-v2",
    collections_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Stateless search function — convenience wrapper for CLI usage."""
    from ..storage import list_collection_names

    names = (
        [c.name for c in configs] if configs else list_collection_names(collections_dir)
    )

    results = _search_collections(
        query,
        names,
        similarity_top_k=max_chunks,
        embed_model_name=embed_model_name,
        max_docs=max_docs,
        include_matched_chunks=include_matched_chunks,
        collections_dir=collections_dir,
    )

    if len(results) == 1:
        return results[0]

    return {"query": query, "collections": results}
