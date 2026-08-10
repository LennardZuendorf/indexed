"""Search service for querying document collections.

This module provides functionality to search across document collections using
various indexing strategies. It supports both stateful (class-based) and stateless
(functional) interfaces for different use cases, with automatic collection discovery
and caching of search indexes for optimal performance.
"""

import errno
import json
import re
from typing import Any

from loguru import logger

from indexed.config.errors import StorageError
from indexed.core.v1.config_models import get_default_collections_path
from indexed.core.v1.engine.factories.search_collection_factory import (
    create_collection_searcher,
)
from indexed.core.v1.engine.persisters.disk_persister import DiskPersister
from indexed.protocols import Manifest

from .models import SourceConfig

# When a score threshold is active, request this many times `max_docs` from
# the searcher so filtered-out slots can be backfilled from the next-best
# surviving documents (bug A5) instead of being lost by an earlier truncation.
_BACKFILL_OVERFETCH_FACTOR = 3

# Transient directories the durable-create path leaves aside:
# `<name>.tmp-<pid>-<hex>` staging dirs and `<name>.trash-<pid>` rollback dirs.
# These must never be reported as real collections (mirrors InspectService).
_INTERNAL_COLLECTION_DIR_RE = re.compile(r"\.(?:tmp|trash)-\d+")


class SearchService:
    """Stateful search service that caches DocumentCollectionSearcher instances.

    This service is designed for long-running processes like MCP servers where FAISS
    indexes should be loaded once and reused across multiple queries. It maintains
    an internal cache of searcher instances to avoid repeated index loading overhead.

    Attributes:
        _searcher_cache (Dict[str, Any]): Internal cache for collection searchers.
        _persister (DiskPersister): Disk persister for reading collection data.

    Example:
        >>> service = SearchService()
        >>> results = service.search("machine learning", max_docs=5)
        >>> for collection, result in results.items():
        ...     print(f"Found {len(result.get('documents', []))} docs in {collection}")
    """

    def __init__(self, collections_path: str | None = None):
        """Initialize the search service with empty cache and default persister.

        Args:
            collections_path: Optional path for collections storage.
                             Defaults to resolved path from storage config.
        """
        self._searcher_cache: dict[str, Any] = {}
        self._collections_path = collections_path or str(get_default_collections_path())
        self._persister = DiskPersister(base_path=self._collections_path)

    def _get_searcher(self, collection_name: str, index_name: str):
        """Get or create a cached searcher for the collection.

        Args:
            collection_name (str): Name of the collection to search.
            index_name (str): Name of the index to use for searching.

        Returns:
            Any: A DocumentCollectionSearcher instance for the specified collection and index.

        Note:
            This method implements caching - subsequent calls for the same collection
            and index combination will return cached instances without reloading.
        """
        cache_key = f"{collection_name}:{index_name}"
        if cache_key not in self._searcher_cache:
            self._searcher_cache[cache_key] = create_collection_searcher(
                collection_name=collection_name,
                index_name=index_name,
                collections_path=self._collections_path,
            )
        return self._searcher_cache[cache_key]

    def _discover_collections(self) -> list[str]:
        """Discover all available collections by scanning the data directory.

        Returns:
            List[str]: List of collection names that contain a valid manifest.json.

        Raises:
            StorageError: If the collections directory cannot be scanned (e.g.
                a permission or transient filesystem error). This is a
                non-recoverable scan failure and must fail loud rather than
                silently report zero collections. A missing top-level
                directory (ENOENT) is NOT a scan failure — a fresh install
                has no collections directory yet — and returns an empty
                list instead (R3).
        """
        try:
            entries = self._persister.read_folder_files(".")
        except Exception as exc:
            if isinstance(exc, OSError) and exc.errno == errno.ENOENT:
                return []
            logger.error(f"Failed to discover collections: {exc}")
            raise StorageError(f"Could not scan collections directory: {exc}") from exc

        # Derive top-level directory candidates from any file path or directory name
        top_level_dirs = set()
        for rel_path in entries:
            if "/" in rel_path:
                parts = rel_path.split("/", 1)
                top_level_dirs.add(parts[0])
            else:
                # Treat bare names as top-level directories too
                top_level_dirs.add(rel_path)
        logger.debug(f"Candidate top-level dirs: {sorted(top_level_dirs)}")

        discovered: list[str] = []
        for dirname in sorted(top_level_dirs):
            # Skip the transient build-aside/rollback directories the
            # durable-create path leaves on disk — see _INTERNAL_COLLECTION_DIR_RE.
            if dirname and _INTERNAL_COLLECTION_DIR_RE.search(dirname):
                continue
            manifest_path = f"{dirname}/manifest.json"
            if self._persister.is_path_exists(manifest_path):
                discovered.append(dirname)

        logger.info(f"Found {len(discovered)} collections: {', '.join(discovered)}")
        return discovered

    def _get_default_indexer(self, collection_name: str) -> str:
        """Get the first indexer from a collection's manifest.

        Args:
            collection_name (str): Name of the collection to get indexer for.

        Returns:
            str: The name of the first indexer found in the collection's manifest,
                 or a default FAISS indexer if the manifest cannot be read.

        Note:
            This method provides a fallback to a standard FAISS indexer configuration
            if the manifest file is corrupted or missing.
        """
        try:
            manifest_content = self._persister.read_text_file(
                f"{collection_name}/manifest.json"
            )
            manifest = Manifest.from_disk(json.loads(manifest_content))
            return manifest.indexers[0].name
        except Exception:
            # Fallback to default indexer
            return "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"

    def _filter_by_score(
        self, result: dict[str, Any], score_threshold: float
    ) -> dict[str, Any]:
        """Filter search results by score threshold.

        Scores are squared-L2 distance in [0, 4] (embeddings are
        unit-normalized) — lower is more similar. This method filters out
        documents where the best (lowest) matching chunk score exceeds the
        threshold, and removes chunks that exceed the threshold within each
        document. Callers should apply this BEFORE truncating to `max_docs`
        so filtered-out slots can be backfilled from the next-best surviving
        documents (bug A5) — truncating first and filtering after would lose
        those candidates permanently.

        Args:
            result (Dict[str, Any]): Search result dictionary containing 'results' key.
            score_threshold (float): Maximum squared-L2 distance allowed.

        Returns:
            Dict[str, Any]: Filtered result with same structure but fewer documents/chunks.
        """
        if "results" not in result:
            return result

        filtered_results = []
        for doc in result["results"]:
            if "matchedChunks" not in doc:
                filtered_results.append(doc)
                continue

            # Filter chunks by score
            filtered_chunks = [
                chunk
                for chunk in doc["matchedChunks"]
                if chunk.get("score", float("inf")) <= score_threshold
            ]

            # Only include document if it has at least one matching chunk
            if filtered_chunks:
                filtered_doc = {**doc, "matchedChunks": filtered_chunks}
                filtered_results.append(filtered_doc)

        return {**result, "results": filtered_results}

    def search(
        self,
        query: str,
        *,
        configs: list[SourceConfig] | None = None,
        max_chunks: int | None = None,
        max_docs: int | None = None,
        score_threshold: float | None = None,
        include_full_text: bool = False,
        include_all_chunks: bool = False,
        include_matched_chunks: bool = False,
    ) -> dict[str, Any]:
        """Search across one or many collections.

        Performs semantic search across specified collections or auto-discovers
        all available collections if none are specified. Results are returned
        as a dictionary with collection names as keys.

        Args:
            query (str): Text query to search for.
            configs (Optional[List[SourceConfig]]): List of source configs specifying
                which collections and indexers to use. If None, auto-discovers all
                available collections and uses their default indexers.
            max_chunks (Optional[int]): Maximum number of chunks to return per collection.
                Defaults to max_docs * 3 if not specified.
            max_docs (Optional[int]): Maximum number of documents to return per collection.
                Defaults to 10 if not specified.
            score_threshold (Optional[float]): Maximum distance score for results.
                Results with scores above this threshold are filtered out. For FAISS
                squared L2 distance, lower scores indicate better matches.
            include_full_text (bool): Whether to include full document text in results.
                Defaults to False.
            include_all_chunks (bool): Whether to include all chunks content in results.
                Defaults to False.
            include_matched_chunks (bool): Whether to include matched chunks content
                in results. Defaults to False.

        Returns:
            Dict[str, Any]: Dictionary with collection names as keys and search results
                           as values. Each result contains documents, chunks, and metadata.
                           Collections that encounter errors will have an 'error' key
                           with the error message.

        Example:
            >>> service = SearchService()
            >>> results = service.search(
            ...     "machine learning algorithms",
            ...     max_docs=5,
            ...     score_threshold=1.5,
            ...     include_matched_chunks=True
            ... )
            >>> for collection, result in results.items():
            ...     if 'error' in result:
            ...         print(f"Error in {collection}: {result['error']}")
            ...     else:
            ...         print(f"Found {len(result['documents'])} docs in {collection}")
        """
        # Apply same defaults as original implementation
        if max_docs is None:
            max_docs = 10
        if max_chunks is None:
            max_chunks = max_docs * 3

        # Determine which collections to search
        if configs is None:
            # Auto-discover mode: find all collections and use their default indexers
            collection_names = self._discover_collections()
            search_configs = []
            for name in collection_names:
                default_indexer = self._get_default_indexer(name)
                # Create minimal config just for search
                search_configs.append(
                    SourceConfig(
                        name=name,
                        type="localFiles",  # Type doesn't matter for search
                        base_url_or_path="",  # Not used for search
                        indexer=default_indexer,
                    )
                )
        else:
            search_configs = configs

        num_collections = len(search_configs) if search_configs else 0
        logger.info(
            f'Searching "{query}" across {num_collections} collection{"s" if num_collections != 1 else ""}'
        )

        results = {}

        for cfg in search_configs:
            try:
                searcher = self._get_searcher(
                    cfg.name, cfg.indexer or self._get_default_indexer(cfg.name)
                )

                # Filter-before-truncate + backfill (bug A5): when a score
                # threshold is active, ask the searcher for more documents
                # than requested so that documents dropped by the filter can
                # be backfilled from the next-best surviving ones, THEN
                # truncate to max_docs after filtering.
                searcher_max_docs = max_docs
                if score_threshold is not None and max_docs is not None:
                    searcher_max_docs = max_docs * _BACKFILL_OVERFETCH_FACTOR

                result = searcher.search(
                    text=query,
                    max_number_of_chunks=max_chunks,
                    max_number_of_documents=searcher_max_docs,
                    include_text_content=include_full_text,
                    include_all_chunks_content=include_all_chunks,
                    include_matched_chunks_content=include_matched_chunks,
                )

                # Apply score threshold filtering if specified
                if score_threshold is not None and isinstance(result, dict):
                    result = self._filter_by_score(result, score_threshold)
                    if max_docs is not None and "results" in result:
                        result = {**result, "results": result["results"][:max_docs]}

                results[cfg.name] = result
                num_docs = (
                    len(result.get("results", [])) if isinstance(result, dict) else 0
                )
                doc_word = "document" if num_docs == 1 else "documents"
                logger.info(f"✓ {cfg.name}: {num_docs} {doc_word}")
            except Exception as e:
                # Log error but continue with other collections
                logger.error(f"Error searching collection {cfg.name}: {e}")
                results[cfg.name] = {"error": str(e)}

        return results


def search(
    query: str,
    configs: list[SourceConfig] | None = None,
    max_chunks: int | None = None,
    max_docs: int | None = None,
    score_threshold: float | None = None,
    include_full_text: bool = False,
    include_all_chunks: bool = False,
    include_matched_chunks: bool = False,
    collections_path: str | None = None,
) -> dict[str, Any]:
    """Functional wrapper around SearchService for one-shot CLI usage.

    This function provides a stateless interface to the search functionality,
    suitable for command-line tools and simple scripts that don't need to
    maintain searcher caches across multiple queries.

    Args:
        query (str): Text query to search for.
        configs (Optional[List[SourceConfig]]): List of source configs specifying
            which collections and indexers to use. If None, auto-discovers all
            available collections.
        max_chunks (Optional[int]): Maximum number of chunks to return per collection.
        max_docs (Optional[int]): Maximum number of documents to return per collection.
        score_threshold (Optional[float]): Maximum distance score for results.
            Results with scores above this threshold are filtered out.
        include_full_text (bool): Whether to include full document text in results.
        include_all_chunks (bool): Whether to include all chunks content in results.
        include_matched_chunks (bool): Whether to include matched chunks content.
        collections_path: Optional path for collections storage.

    Returns:
        Dict[str, Any]: Dictionary with collection names as keys and search results
                       as values. See SearchService.search() for detailed format.

    Example:
        >>> from core.v1.engine.services.search_service import search
        >>> results = search("python programming", max_docs=3, score_threshold=1.5)
        >>> print(f"Searched {len(results)} collections")
    """
    # Stateless per-call service — no module-level singleton (foundation/9).
    # SearchService still caches loaded FAISS searchers for the life of the
    # instance; a long-lived server should hold its own SearchService.
    service = SearchService(collections_path=collections_path)
    return service.search(
        query=query,
        configs=configs,
        max_chunks=max_chunks,
        max_docs=max_docs,
        score_threshold=score_threshold,
        include_full_text=include_full_text,
        include_all_chunks=include_all_chunks,
        include_matched_chunks=include_matched_chunks,
    )
