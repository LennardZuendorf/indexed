"""Search service for querying document collections.

This module provides functionality to search across document collections using
various indexing strategies. It supports both stateful (class-based) and stateless
(functional) interfaces for different use cases, with automatic collection discovery
and caching of search indexes for optimal performance.
"""

import json
from typing import List, Optional, Dict, Any
from .models import SourceConfig
from ..utils.logger import setup_root_logger
from ..persisters.disk_persister import DiskPersister
from ..factories.search_collection_factory import create_collection_searcher

setup_root_logger()


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
            List[str]: List of collection names found in the data directory.
                      Only directories with valid manifest.json files are included.

        Note:
            This method scans the base data directory and validates that each
            potential collection has a proper manifest file before including it.
        """
        try:
            return [
                name
                for name in self._persister.read_folder_files(".")
                if self._persister.is_path_exists(f"{name}/manifest.json")
            ]
        except Exception:
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
        # Apply same defaults as legacy adapter
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

        results = {}
        for cfg in search_configs:
            try:
                searcher = self._get_searcher(cfg.name, cfg.indexer)
                result = searcher.search(
                    query,
                    max_number_of_chunks=max_chunks,
                    max_number_of_documents=max_docs,
                    include_text_content=include_full_text,
                    include_all_chunks_content=include_all_chunks,
                    include_matched_chunks_content=include_matched_chunks,
                )
                results[cfg.name] = result
            except Exception as e:
                # Log error but continue with other collections
                import logging

                logging.error(f"Error searching collection {cfg.name}: {e}")
                results[cfg.name] = {"error": str(e)}

        return results


# Global singleton for functional interface
_default_service = SearchService()


def search(
    query: str,
    *,
    configs: Optional[List[SourceConfig]] = None,
    max_chunks: Optional[int] = None,
    max_docs: Optional[int] = None,
    include_full_text: bool = False,
    include_all_chunks: bool = False,
    include_matched_chunks: bool = False,
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
        >>> from main.services.search_service import search
        >>> results = search("python programming", max_docs=3)
        >>> print(f"Searched {len(results)} collections")
    """
    return _default_service.search(
        query,
        configs=configs,
        max_chunks=max_chunks,
        max_docs=max_docs,
        include_full_text=include_full_text,
        include_all_chunks=include_all_chunks,
        include_matched_chunks=include_matched_chunks,
    )
