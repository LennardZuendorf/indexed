"""Inspect service for examining document collections.

This module provides functionality to inspect and analyze document collections,
including retrieving status information, metadata, and index statistics. It supports
both stateful (class-based) and stateless (functional) interfaces for different
use cases.
"""

import json
from typing import List, Optional, Dict
import os
from .models import CollectionStatus
from ..utils.logger import setup_root_logger
from ..persisters.disk_persister import DiskPersister
from ..indexes.indexer_factory import load_indexer

setup_root_logger()


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

    def __init__(self):
        """Initialize the inspect service with empty cache and default persister."""
        self._manifest_cache: Dict[str, dict] = {}
        self._persister = DiskPersister(base_path="./data/collections")

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
                    collection_name = os.path.dirname(item).split(os.sep)[0] or os.path.dirname(item)
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
    ) -> List[CollectionStatus]:
        """Get status information for collections.

        Args:
            collection_names (Optional[List[str]]): List of collection names to inspect.
                                                   If None, all available collections
                                                   will be discovered and inspected.
            include_index_size (bool): Whether to include index size information.
                                     This requires loading the indexer and may be
                                     slower. Defaults to False.

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
        for name in collection_names:
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
                        import logging

                        logging.warning(f"Could not get index size for {name}: {e}")

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
                import logging

                logging.error(f"Error getting status for collection {name}: {e}")
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


# Global singleton for functional interface
_default_service = InspectService()


def status(
    collection_names: Optional[List[str]] = None,
    *,
    include_index_size: bool = False,
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

    Returns:
        List[CollectionStatus]: List of status objects containing metadata
                               for each requested collection.

    Example:
        >>> from main.services.inspect_service import status
        >>> # Get status for all collections
        >>> all_statuses = status()
        >>> # Get status for specific collections
        >>> specific_statuses = status(['my_collection'])

    Note:
        This function uses a global singleton InspectService instance, so manifest
        data will be cached across multiple calls within the same process.
    """
    return _default_service.status(
        collection_names=collection_names,
        include_index_size=include_index_size,
    )
