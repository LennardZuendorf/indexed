from pathlib import Path
from typing import Optional

from core.v1.engine.persisters.disk_persister import DiskPersister
from core.v1.engine.indexes.indexer_factory import load_indexer
from core.v1.engine.core.documents_collection_searcher import DocumentCollectionSearcher

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


def create_collection_searcher(
    collection_name,
    index_name,
    collections_path: Optional[str] = None,
):
    """Create a collection searcher instance.
    
    Args:
        collection_name: Name of the collection to search.
        index_name: Name of the index to use.
        collections_path: Optional path for collections storage.
                         Defaults to resolved path from storage config.
    """
    return log_execution_duration(
        lambda: __create_collection_searcher(
            collection_name, index_name, collections_path
        ),
        identifier="Preparing collection searcher",
    )


def __create_collection_searcher(
    collection_name,
    index_name,
    collections_path: Optional[str] = None,
):
    resolved_path = collections_path or _get_default_collections_path()
    disk_persister = DiskPersister(base_path=resolved_path)

    indexer = load_indexer(index_name, collection_name, disk_persister)

    return DocumentCollectionSearcher(
        collection_name=collection_name, indexer=indexer, persister=disk_persister
    )