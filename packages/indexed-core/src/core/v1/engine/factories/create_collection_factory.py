from pathlib import Path
from typing import Optional

from connectors.document_cache_reader_decorator import CacheReaderDecorator
from core.v1.engine.core.documents_collection_creator import (
    DocumentCollectionCreator,
    OPERATION_TYPE,
)
from core.v1.engine.indexes.indexer_factory import create_indexer
from core.v1.engine.persisters.disk_persister import DiskPersister

from utils.performance import log_execution_duration


def _get_default_collections_path() -> str:
    """Get the default collections path from storage config."""
    try:
        from indexed_config import get_resolver

        resolver = get_resolver()
        return str(resolver.get_collections_path())
    except ImportError:
        # Fallback if indexed_config not available
        return str(Path.home() / ".indexed" / "data" / "collections")


def _get_default_caches_path() -> str:
    """Get the default caches path from storage config."""
    try:
        from indexed_config import get_resolver

        resolver = get_resolver()
        return str(resolver.get_caches_path())
    except ImportError:
        # Fallback if indexed_config not available
        from pathlib import Path

        return str(Path.home() / ".indexed" / "data" / "caches")


def create_collection_creator(
    collection_name,
    indexers,
    document_reader,
    document_converter,
    use_cache=True,
    progress_callback=None,
    collections_path: Optional[str] = None,
    caches_path: Optional[str] = None,
):
    """Create a collection creator instance.

    Args:
        collection_name: Name of the collection to create.
        indexers: List of indexer names to use.
        document_reader: Document reader instance.
        document_converter: Document converter instance.
        use_cache: Whether to use caching for document reading.
        progress_callback: Optional callback for progress updates.
        collections_path: Optional path for collections storage.
                         Defaults to resolved path from storage config.
        caches_path: Optional path for caches storage.
                    Defaults to resolved path from storage config.
    """
    return log_execution_duration(
        lambda: __create_collection_creator(
            collection_name,
            indexers,
            document_reader,
            document_converter,
            use_cache,
            progress_callback,
            collections_path,
            caches_path,
        ),
        identifier="Preparing collection creator",
    )


def __create_collection_creator(
    collection_name,
    indexers,
    document_reader,
    document_converter,
    use_cache,
    progress_callback=None,
    collections_path: Optional[str] = None,
    caches_path: Optional[str] = None,
):
    # Resolve paths
    resolved_collections_path = collections_path or _get_default_collections_path()
    resolved_caches_path = caches_path or _get_default_caches_path()

    if use_cache:
        cache_disk_persister = DiskPersister(base_path=resolved_caches_path)
        result_document_reader = CacheReaderDecorator(
            reader=document_reader, persister=cache_disk_persister
        )
    else:
        result_document_reader = document_reader

    document_indexers = [create_indexer(indexer_name) for indexer_name in indexers]

    disk_persister = DiskPersister(base_path=resolved_collections_path)

    return DocumentCollectionCreator(
        collection_name=collection_name,
        document_reader=result_document_reader,
        document_converter=document_converter,
        document_indexers=document_indexers,
        persister=disk_persister,
        operation_type=OPERATION_TYPE.CREATE,
        progress_callback=progress_callback,
    )
