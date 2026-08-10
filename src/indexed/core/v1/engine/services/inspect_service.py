"""Inspect service for examining document collections.

This module provides functionality to inspect and analyze document collections,
including retrieving status information, metadata, and index statistics. It supports
both stateful (class-based) and stateless (functional) interfaces for different
use cases.
"""

import errno
import json
import os
import re

from loguru import logger

from indexed.config.errors import StorageError
from indexed.core.v1.config_models import get_default_collections_path
from indexed.core.v1.engine.indexes.indexer_factory import load_indexer
from indexed.core.v1.engine.persisters.disk_persister import DiskPersister

from .models import CollectionInfo, CollectionStatus

# Transient directories the durable-create path leaves aside:
# `<name>.tmp-<pid>-<hex>` staging dirs and `<name>.trash-<pid>` rollback dirs.
# These must never be reported as real collections.
_INTERNAL_COLLECTION_DIR_RE = re.compile(r"\.(?:tmp|trash)-\d+")


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

    def __init__(self, collections_path: str | None = None):
        """Initialize the inspect service with empty cache and default persister.

        Args:
            collections_path: Optional path for collections storage.
                             Defaults to resolved path from storage config.
        """
        self._manifest_cache: dict[str, dict] = {}
        resolved_path = collections_path or str(get_default_collections_path())
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

    def _discover_collections(self) -> list[str]:
        """Discover all available collections by scanning the data directory.

        Returns:
            List[str]: List of collection names found in the data directory.
                      Only directories containing a manifest.json file are considered
                      valid collections.

        Raises:
            StorageError: If the collections directory cannot be scanned (e.g.
                a permission or transient filesystem error). This is a
                non-recoverable scan failure and must fail loud rather than
                silently report zero collections — distinct from the
                per-collection manifest errors tolerated in status()/inspect().
                A missing top-level directory (ENOENT) is NOT a scan failure —
                a fresh install has no collections directory yet — and
                returns an empty list instead (R3).
        """
        try:
            # Find any files named manifest.json and derive collection name from their parent folder
            all_items = self._persister.read_folder_files(".")
        except Exception as e:
            if isinstance(e, OSError) and e.errno == errno.ENOENT:
                return []
            logger.error(f"Error scanning collections directory: {e}")
            raise StorageError(f"Could not scan collections directory: {e}") from e

        collections = set()
        for item in all_items:
            if os.path.basename(item) == "manifest.json":
                # Parent directory name is the collection name
                collection_name = os.path.dirname(item).split(os.sep)[
                    0
                ] or os.path.dirname(item)
                # Skip the transient build-aside/rollback directories the
                # durable-create path leaves on disk (`<name>.tmp-<pid>-<hex>`
                # staging dirs; `<name>.trash-<pid>` swap-rollback dirs). A
                # hard kill mid-create, or a failed cleanup, can otherwise
                # leave a valid manifest in one of these and surface it as a
                # phantom collection in status/search/inspect.
                if collection_name and not _INTERNAL_COLLECTION_DIR_RE.search(
                    collection_name
                ):
                    collections.add(collection_name)
        return sorted(collections)

    def _calculate_disk_size(self, collection_name: str) -> int:
        base_dir = os.path.join(self._persister.base_path, collection_name)
        return self._calculate_dir_size(base_dir)

    def _calculate_documents_size(self, collection_name: str) -> int:
        """Byte total of the ``documents/`` subfolder only (F3).

        Used to compute ``avg_doc_size_bytes`` from document content alone,
        excluding the manifest and the FAISS index files that also live under
        the collection directory.
        """
        docs_dir = os.path.join(self._persister.base_path, collection_name, "documents")
        return self._calculate_dir_size(docs_dir)

    @staticmethod
    def _calculate_dir_size(base_dir: str) -> int:
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

    def _get_index_file_size_bytes(
        self, collection_name: str, indexer_name: str
    ) -> int | None:
        """Real on-disk byte size of the collection's FAISS index file (F1).

        This is a file size via ``os.path.getsize`` — distinct from
        ``indexer.get_size()`` (the FAISS ``ntotal`` vector count), which was
        previously reported here as if it were a byte size.
        """
        index_path = os.path.join(
            self._persister.base_path,
            collection_name,
            "indexes",
            indexer_name,
            "indexer.faiss",
        )
        try:
            return os.path.getsize(index_path)
        except OSError:
            return None

    def status(
        self,
        collection_names: list[str] | None = None,
        *,
        include_index_size: bool = False,
    ) -> list[CollectionStatus]:
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
                                   that are missing or whose manifest cannot be
                                   read are OMITTED from the result rather than
                                   returned as a zero-filled placeholder.

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
                # Missing/unreadable collections are OMITTED, not zero-filled —
                # a placeholder here would defeat every downstream "not found"
                # guard (see foundation/6 E1/E11).
                logger.error(f"Error getting status for collection {name}: {e}")

        return statuses

    def inspect(
        self,
        collection_names: list[str] | None = None,
        *,
        include_index_size: bool = False,
    ) -> list[CollectionInfo]:
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

        Returns:
            List[CollectionInfo]: List of detailed info objects containing comprehensive
                                 metadata and computed statistics for each collection.
                                 Collections that are missing or whose manifest cannot
                                 be read are OMITTED, not returned as a zero-filled
                                 placeholder.

        Example:
            >>> service = InspectService()
            >>> # Get detailed info for specific collection
            >>> info = service.inspect(['my_collection'])
            >>> print(f"Avg chunks/doc: {info[0].avg_chunks_per_doc:.1f}")
        """
        if collection_names is None:
            collection_names = self._discover_collections()

        infos = []

        for name in collection_names:
            try:
                manifest = self._read_manifest(name)

                # F1: the real on-disk byte size of the index file — distinct
                # from the FAISS vector count (already reported via
                # number_of_chunks); never format a vector count as bytes.
                index_size_bytes = None
                if include_index_size and manifest.get("indexers"):
                    try:
                        first_indexer = manifest["indexers"][0]["name"]
                        index_size_bytes = self._get_index_file_size_bytes(
                            name, first_indexer
                        )
                    except Exception as e:
                        logger.warning(f"Could not get index size for {name}: {e}")

                # Gather all metadata
                source_type = manifest.get("reader", {}).get("type")
                abs_path = os.path.join(self._persister.base_path, name)
                relative_path = os.path.relpath(abs_path, start=os.getcwd())
                disk_size = self._calculate_disk_size(name)
                number_of_documents = manifest.get("numberOfDocuments", 0)

                # F3: average document size computed from document bytes
                # only (excludes the manifest/index files also present under
                # disk_size_bytes), passed explicitly so CollectionInfo's
                # __post_init__ doesn't fall back to the disk-size-inclusive
                # calculation.
                avg_doc_size_bytes = None
                if number_of_documents > 0:
                    avg_doc_size_bytes = (
                        self._calculate_documents_size(name) / number_of_documents
                    )

                # Build CollectionInfo (avg_chunks_per_doc computed in
                # __post_init__)
                info = CollectionInfo(
                    name=name,
                    source_type=source_type,
                    number_of_documents=number_of_documents,
                    number_of_chunks=manifest.get("numberOfChunks", 0),
                    relative_path=relative_path,
                    disk_size_bytes=disk_size,
                    index_size_bytes=index_size_bytes,
                    avg_doc_size_bytes=avg_doc_size_bytes,
                    created_time=manifest.get("createdTime"),
                    updated_time=manifest.get("updatedTime", ""),
                    last_modified_document_time=manifest.get(
                        "lastModifiedDocumentTime", ""
                    ),
                    indexers=[idx["name"] for idx in manifest.get("indexers", [])],
                )
                infos.append(info)

            except Exception as e:
                # Missing/unreadable collections are OMITTED, not zero-filled —
                # see status() above for the same rationale.
                logger.error(f"Error inspecting collection {name}: {e}")

        return infos


def status(
    collection_names: list[str] | None = None,
    *,
    include_index_size: bool = False,
    collections_path: str | None = None,
) -> list[CollectionStatus]:
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
        Builds a fresh InspectService per call (stateless). A long-lived process
        that wants cross-call manifest caching should hold its own InspectService.
    """
    service = InspectService(collections_path=collections_path)
    return service.status(
        collection_names=collection_names,
        include_index_size=include_index_size,
    )


def inspect(
    collection_names: list[str] | None = None,
    *,
    include_index_size: bool = False,
    collections_path: str | None = None,
) -> list[CollectionInfo]:
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
        Builds a fresh InspectService per call (stateless).
    """
    service = InspectService(collections_path=collections_path)
    return service.inspect(
        collection_names=collection_names,
        include_index_size=include_index_size,
    )
