"""Search service for querying document collections.

This module provides functionality to search across document collections using
various indexing strategies. It supports both stateful (class-based) and stateless
(functional) interfaces for different use cases, with automatic collection discovery
and caching of search indexes for optimal performance.
"""

import json
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger

from .models import SourceConfig, ProgressUpdate, ProgressCallback
from core.v1.engine.persisters.disk_persister import DiskPersister
from core.v1.engine.factories.search_collection_factory import (
    create_collection_searcher,
)


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

    def __init__(self):
        """Initialize the search service with empty cache and default persister."""
        self._searcher_cache: Dict[str, Any] = {}
        self._persister = DiskPersister(base_path="./data/collections")

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
                collection_name=collection_name, index_name=index_name
            )
        return self._searcher_cache[cache_key]

    def _discover_collections(self) -> List[str]:
        """Discover all available collections by scanning the data directory.

        Returns:
            List[str]: List of collection names that contain a valid manifest.json.
        """
        try:
            entries = self._persister.read_folder_files(".")
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

            discovered: List[str] = []
            for dirname in sorted(top_level_dirs):
                manifest_path = f"{dirname}/manifest.json"
                if self._persister.is_path_exists(manifest_path):
                    discovered.append(dirname)

            logger.info(f"Found {len(discovered)} collections: {', '.join(discovered)}")
            return discovered
        except Exception as exc:
            logger.error(f"Failed to discover collections: {exc}")
            return []

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
            manifest = json.loads(manifest_content)
            return manifest["indexers"][0]["name"]
        except Exception:
            # Fallback to default indexer
            return "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"

    def search(
        self,
        query: str,
        *,
        configs: Optional[List[SourceConfig]] = None,
        max_chunks: Optional[int] = None,
        max_docs: Optional[int] = None,
        include_full_text: bool = False,
        include_all_chunks: bool = False,
        include_matched_chunks: bool = False,
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, Any]:
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
        total_collections = len(search_configs)

        for idx, cfg in enumerate(search_configs, 1):
            if progress_callback:
                progress_callback(
                    ProgressUpdate(
                        stage="searching",
                        current=idx,
                        total=total_collections,
                        message=f"Searching collection: {cfg.name} ({idx}/{total_collections})",
                    )
                )

            try:
                searcher = self._get_searcher(cfg.name, cfg.indexer)
                result = searcher.search(
                    query=query,
                    max_number_of_chunks=max_chunks,
                    max_number_of_documents=max_docs,
                    include_text_content=include_full_text,
                    include_all_chunks_content=include_all_chunks,
                    include_matched_chunks_content=include_matched_chunks,
                )
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


# Global singleton for functional interface
_default_service = SearchService()


def search(
    query: str,
    configs: Optional[List[SourceConfig]] = None,
    max_chunks: Optional[int] = None,
    max_docs: Optional[int] = None,
    include_full_text: bool = False,
    include_all_chunks: bool = False,
    include_matched_chunks: bool = False,
    progress_callback: ProgressCallback = None,
) -> Dict[str, Any]:
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
        include_full_text (bool): Whether to include full document text in results.
        include_all_chunks (bool): Whether to include all chunks content in results.
        include_matched_chunks (bool): Whether to include matched chunks content.

    Returns:
        Dict[str, Any]: Dictionary with collection names as keys and search results
                       as values. See SearchService.search() for detailed format.

    Example:
        >>> from core.v1.engine.services.search_service import search
        >>> results = search("python programming", max_docs=3)
        >>> print(f"Searched {len(results)} collections")
    """
    return _default_service.search(
        query=query,
        configs=configs,
        max_chunks=max_chunks,
        max_docs=max_docs,
        include_full_text=include_full_text,
        include_all_chunks=include_all_chunks,
        include_matched_chunks=include_matched_chunks,
        progress_callback=progress_callback,
    )


# DTO for injected config
@dataclass
class SearchArgs:
    configs: Optional[List[SourceConfig]]
    max_chunks: Optional[int]
    max_docs: Optional[int]
    include_full_text: bool
    include_all_chunks: bool
    include_matched_chunks: bool
