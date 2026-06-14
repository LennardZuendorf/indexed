"""Search service — stateful and stateless search interfaces."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from .models import SourceConfig

logger = logging.getLogger(__name__)


def _all_v2_collection_names(collections_dir: Optional[Path]) -> list[str]:
    """All v2 collections under ``collections_dir``; non-v2 ones are skipped.

    The all-collections search path must not abort when a v1 (legacy) collection
    shares the directory. It filters to v2 stores and logs what it skipped so a
    mixed v1/v2 repo still returns its v2 results rather than erroring on the
    first v1 collection encountered.
    """
    from ..storage import detect_disk_engine, list_collection_names

    names = list_collection_names(collections_dir)
    v2_names = [n for n in names if detect_disk_engine(n, collections_dir) == "v2"]
    skipped = [n for n in names if n not in v2_names]
    if skipped:
        logger.info(
            "v2 search: skipping %d non-v2 collection(s): %s",
            len(skipped),
            ", ".join(skipped),
        )
    return v2_names


def _search_collections(
    query: str,
    names: list[str],
    *,
    similarity_top_k: int = 30,
    embed_model_name: str = "all-MiniLM-L6-v2",
    max_docs: int = 10,
    include_matched_chunks: bool = True,
    score_threshold: Optional[float] = None,
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
            score_threshold=score_threshold,
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
        score_threshold: Optional[float] = None,
    ) -> dict[str, Any]:
        """Search a specific collection or all collections."""
        if collection_name:
            names = [collection_name]
        else:
            names = _all_v2_collection_names(self._collections_dir)

        results = _search_collections(
            query,
            names,
            similarity_top_k=similarity_top_k,
            embed_model_name=self._embed_model_name,
            max_docs=max_docs,
            include_matched_chunks=include_matched_chunks,
            score_threshold=score_threshold,
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
    score_threshold: Optional[float] = None,
    embed_model_name: str = "all-MiniLM-L6-v2",
    collections_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Stateless search function — convenience wrapper for CLI usage."""
    names = (
        [c.name for c in configs]
        if configs is not None
        else _all_v2_collection_names(collections_dir)
    )

    results = _search_collections(
        query,
        names,
        similarity_top_k=max_chunks,
        embed_model_name=embed_model_name,
        max_docs=max_docs,
        include_matched_chunks=include_matched_chunks,
        score_threshold=score_threshold,
        collections_dir=collections_dir,
    )

    if len(results) == 1:
        return results[0]

    return {"query": query, "collections": results}
