"""Inspect service for examining document collections.

This module provides functionality to inspect and analyze document collections,
including retrieving status information, metadata, and index statistics. It supports
both stateful (class-based) and stateless (functional) interfaces for different
use cases.
"""

import json
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass
import os

from loguru import logger

from .models import CollectionStatus, CollectionInfo, ProgressUpdate, ProgressCallback
from utils.logger import setup_root_logger
from core.v1.engine.persisters.disk_persister import DiskPersister
from core.v1.engine.indexes.indexer_factory import load_indexer

setup_root_logger()


def _get_default_collections_path() -> str:
    """Get the default collections path from storage config."""
    try:
        from indexed_config import get_resolver
        resolver = get_resolver()
        return str(resolver.get_collections_path())
    except ImportError:
        # Fallback if indexed_config not available
        return str(Path.home() / ".indexed" / "data" / "collections")


class InspectService:
    """Stateful inspect service that can cache manifest data.

    This service is designed for long-running processes like MCP servers where manifest
    data can be cached to avoid repeated disk I/O operations. It maintains an internal
    cache of collection manifests and provides methods to inspect collection status
    and metadata.

    Attributes:
        _manifest_cache (Dict[str, dict]): Internal cache for collection manifests.
        _persister (DiskPersister): Disk persister for reading collection data.

    Example:
        >>> service = InspectService()
        >>> statuses = service.status(['my_collection'])
        >>> print(f"Collection has {statuses[0].number_of_documents} documents")
    """

    def __init__(self, collections_path: Optional[str] = None):
        """Initialize the inspect service with empty cache and default persister.
        
        Args:
            collections_path: Optional path for collections storage.
                             Defaults to resolved path from storage config.
        """
        self._manifest_cache: Dict[str, dict] = {}
        resolved_path = collections_path or _get_default_collections_path()
        self._persister = DiskPersister(base_path=resolved_path)

    def _read_manifest(self, collection_name: str) -> dict:
        """Read and cache manifest for a collection.

        Args:
            collection_name (str): Name of the collection to read manifest for.

        Returns:
            dict: The parsed manifest data for the collection.

        Raises:
            ValueError: If the manifest file cannot be read or parsed.

        Note:
            This method implements caching - subsequent calls for the same collection
            will return cached data without disk I/O.
        """
        if collection_name not in self._manifest_cache:
            try:
                manifest_content = self._persister.read_text_file(
                    f"{collection_name}/manifest.json"
                )
                self._manifest_cache[collection_name] = json.loads(manifest_content)
            except Exception as e:
                raise ValueError(
                    f"Could not read manifest for collection {collection_name}: {e}"
                )
        return self._manifest_cache[collection_name]

    def _discover_collections(self) -> List[str]:
        """Discover all available collections by scanning the data directory.

        Returns:
            List[str]: List of collection names found in the data directory.
                      Only directories containing a manifest.json file are considered
                      valid collections.

        Note:
            This method silently handles errors and returns an empty list if the
            data directory cannot be accessed.
        """
        try:
            # Find any files named manifest.json and derive collection name from their parent folder
            all_items = self._persister.read_folder_files(".")
            collections = set()
            for item in all_items:
                if os.path.basename(item) == "manifest.json":
                    # Parent directory name is the collection name
                    collection_name = os.path.dirname(item).split(os.sep)[
                        0
                    ] or os.path.dirname(item)
                    if collection_name:
                        collections.add(collection_name)
            return sorted(collections)
        except Exception:
            return []

    def _calculate_disk_size(self, collection_name: str) -> int:
        base_dir = os.path.join(self._persister.base_path, collection_name)
        total = 0
        for root, _dirs, files in os.walk(base_dir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    # Ignore files that cannot be accessed
                    pass
        return total

    def status(
        self,
        collection_names: Optional[List[str]] = None,
        *,
        include_index_size: bool = False,
        progress_callback: ProgressCallback = None,
    ) -> List[CollectionStatus]:
        """Get status information for collections.

        Args:
            collection_names (Optional[List[str]]): List of collection names to inspect.
                                                   If None, all available collections
                                                   will be discovered and inspected.
            include_index_size (bool): Whether to include index size information.
                                     This requires loading the indexer and may be
                                     slower. Defaults to False.
            progress_callback (ProgressCallback, optional): Callback for progress updates.

        Returns:
            List[CollectionStatus]: List of status objects containing metadata
                                   for each requested collection. Collections
                                   that cannot be read will have default/empty
                                   values but will still be included in the result.

        Example:
            >>> service = InspectService()
            >>> # Get status for all collections
            >>> all_statuses = service.status()
            >>> # Get status for specific collections with index size
            >>> specific_statuses = service.status(
            ...     ['collection1', 'collection2'],
            ...     include_index_size=True
            ... )
        """
        if collection_names is None:
            collection_names = self._discover_collections()

        statuses = []
        total = len(collection_names)

        for idx, name in enumerate(collection_names, 1):
            if progress_callback:
                progress_callback(
                    ProgressUpdate(
                        stage="inspecting",
                        current=idx,
                        total=total,
                        message=f"Inspecting: {name} ({idx}/{total})",
                    )
                )
            try:
                manifest = self._read_manifest(name)

                # Get index size if requested
                index_size = None
                if include_index_size and manifest.get("indexers"):
                    try:
                        first_indexer = manifest["indexers"][0]["name"]
                        indexer = load_indexer(first_indexer, name, self._persister)
                        index_size = indexer.get_size()
                    except Exception as e:
                        logger.warning(f"Could not get index size for {name}: {e}")

                # Additional metadata
                source_type = manifest.get("reader", {}).get("type")
                abs_path = os.path.join(self._persister.base_path, name)
                relative_path = os.path.relpath(abs_path, start=os.getcwd())
                disk_size = self._calculate_disk_size(name)

                status = CollectionStatus(
                    name=name,
                    number_of_documents=manifest.get("numberOfDocuments", 0),
                    number_of_chunks=manifest.get("numberOfChunks", 0),
                    updated_time=manifest.get("updatedTime", ""),
                    last_modified_document_time=manifest.get(
                        "lastModifiedDocumentTime", ""
                    ),
                    indexers=[idx["name"] for idx in manifest.get("indexers", [])],
                    index_size=index_size,
                    source_type=source_type,
                    relative_path=relative_path,
                    disk_size_bytes=disk_size,
                )
                statuses.append(status)

            except Exception as e:
                logger.error(f"Error getting status for collection {name}: {e}")
                # Add error status
                statuses.append(
                    CollectionStatus(
                        name=name,
                        number_of_documents=0,
                        number_of_chunks=0,
                        updated_time="",
                        last_modified_document_time="",
                        indexers=[],
                        index_size=None,
                        source_type=None,
                        relative_path=None,
                        disk_size_bytes=None,
                    )
                )

        return statuses

    def inspect(
        self,
        collection_names: Optional[List[str]] = None,
        *,
        include_index_size: bool = False,
        progress_callback: ProgressCallback = None,
    ) -> List[CollectionInfo]:
        """Get detailed inspection information for collections.

        This method returns enhanced CollectionInfo objects with computed statistics
        and all available metadata. It's designed for detailed inspection views.

        Args:
            collection_names (Optional[List[str]]): List of collection names to inspect.
                                                   If None, all available collections
                                                   will be discovered and inspected.
            include_index_size (bool): Whether to include index size information.
                                     This requires loading the indexer and may be
                                     slower. Defaults to False.
            progress_callback (ProgressCallback, optional): Callback for progress updates.

        Returns:
            List[CollectionInfo]: List of detailed info objects containing comprehensive
                                 metadata and computed statistics for each collection.

        Example:
            >>> service = InspectService()
            >>> # Get detailed info for specific collection
            >>> info = service.inspect(['my_collection'])
            >>> print(f"Avg chunks/doc: {info[0].avg_chunks_per_doc:.1f}")
        """
        if collection_names is None:
            collection_names = self._discover_collections()

        infos = []
        total = len(collection_names)

        for idx, name in enumerate(collection_names, 1):
            if progress_callback:
                progress_callback(
                    ProgressUpdate(
                        stage="inspecting",
                        current=idx,
                        total=total,
                        message=f"Inspecting: {name} ({idx}/{total})",
                    )
                )
            try:
                manifest = self._read_manifest(name)

                # Get index size if requested
                index_size = None
                if include_index_size and manifest.get("indexers"):
                    try:
                        first_indexer = manifest["indexers"][0]["name"]
                        indexer = load_indexer(first_indexer, name, self._persister)
                        index_size = indexer.get_size()
                    except Exception as e:
                        logger.warning(f"Could not get index size for {name}: {e}")

                # Gather all metadata
                source_type = manifest.get("reader", {}).get("type")
                abs_path = os.path.join(self._persister.base_path, name)
                relative_path = os.path.relpath(abs_path, start=os.getcwd())
                disk_size = self._calculate_disk_size(name)

                # Build CollectionInfo (averages computed in __post_init__)
                info = CollectionInfo(
                    name=name,
                    source_type=source_type,
                    number_of_documents=manifest.get("numberOfDocuments", 0),
                    number_of_chunks=manifest.get("numberOfChunks", 0),
                    relative_path=relative_path,
                    disk_size_bytes=disk_size,
                    index_size_bytes=index_size,
                    created_time=manifest.get("createdTime"),
                    updated_time=manifest.get("updatedTime", ""),
                    last_modified_document_time=manifest.get(
                        "lastModifiedDocumentTime", ""
                    ),
                    indexers=[idx["name"] for idx in manifest.get("indexers", [])],
                )
                infos.append(info)

            except Exception as e:
                logger.error(f"Error inspecting collection {name}: {e}")
                # Add minimal error info
                infos.append(
                    CollectionInfo(
                        name=name,
                        source_type=None,
                        number_of_documents=0,
                        number_of_chunks=0,
                    )
                )

        return infos


# Global singleton for functional interface (lazily initialized)
_default_service: Optional[InspectService] = None


def _get_service(collections_path: Optional[str] = None) -> InspectService:
    """Get or create the default InspectService instance."""
    global _default_service
    if _default_service is None or collections_path is not None:
        # Create new service with specified path, or use default
        _default_service = InspectService(collections_path=collections_path)
    return _default_service


def status(
    collection_names: Optional[List[str]] = None,
    *,
    include_index_size: bool = False,
    progress_callback: ProgressCallback = None,
    collections_path: Optional[str] = None,
) -> List[CollectionStatus]:
    """Functional wrapper around InspectService for one-shot CLI usage.

    This function provides a stateless interface to the inspect functionality,
    suitable for command-line tools and scripts that don't need to maintain
    state between calls.

    Args:
        collection_names (Optional[List[str]]): List of collection names to inspect.
                                               If None, all available collections
                                               will be discovered and inspected.
        include_index_size (bool): Whether to include index size information.
                                 This requires loading the indexer and may be
                                 slower. Defaults to False.
        collections_path: Optional path for collections storage.

    Returns:
        List[CollectionStatus]: List of status objects containing metadata
                               for each requested collection.

    Example:
        >>> from core.v1.engine.services.inspect_service import status
        >>> # Get status for all collections
        >>> all_statuses = status()
        >>> # Get status for specific collections
        >>> specific_statuses = status(['my_collection'])

    Note:
        This function uses a global singleton InspectService instance, so manifest
        data will be cached across multiple calls within the same process.
    """
    service = _get_service(collections_path)
    return service.status(
        collection_names=collection_names,
        include_index_size=include_index_size,
        progress_callback=progress_callback,
    )


def inspect(
    collection_names: Optional[List[str]] = None,
    *,
    include_index_size: bool = False,
    progress_callback: ProgressCallback = None,
    collections_path: Optional[str] = None,
) -> List[CollectionInfo]:
    """Functional wrapper for detailed collection inspection.

    This function provides a stateless interface to get detailed collection
    information with computed statistics, suitable for CLI inspection commands.

    Args:
        collection_names (Optional[List[str]]): List of collection names to inspect.
                                               If None, all available collections
                                               will be discovered and inspected.
        include_index_size (bool): Whether to include index size information.
                                 This requires loading the indexer and may be
                                 slower. Defaults to False.
        collections_path: Optional path for collections storage.

    Returns:
        List[CollectionInfo]: List of detailed info objects containing comprehensive
                             metadata and computed statistics for each collection.

    Example:
        >>> from core.v1.engine.services.inspect_service import inspect
        >>> # Get detailed info for specific collection
        >>> info = inspect(['my_collection'])
        >>> print(f"Collection has {info[0].number_of_documents} documents")
        >>> print(f"Avg chunks/doc: {info[0].avg_chunks_per_doc:.1f}")

    Note:
        This function uses a global singleton InspectService instance.
    """
    service = _get_service(collections_path)
    return service.inspect(
        collection_names=collection_names,
        include_index_size=include_index_size,
        progress_callback=progress_callback,
    )


# DTO for injected config
@dataclass
class InspectArgs:
    include_index_size: bool = False
