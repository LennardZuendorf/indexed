from typing import Optional

from connectors.document_cache_reader_decorator import CacheReaderDecorator
from core.v1.engine.core.documents_collection_creator import (
    DocumentCollectionCreator,
    OPERATION_TYPE,
)
from core.v1.engine.indexes.indexer_factory import create_indexer
from core.v1.engine.persisters.disk_persister import DiskPersister
from core.v1.config_models import get_default_collections_path, get_default_caches_path

from utils.performance import log_execution_duration


def create_collection_creator(
    collection_name,
    indexers,
    document_reader,
    document_converter,
    use_cache=True,
    progress_callback=None,
    phased_progress=None,
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
        progress_callback: Optional callback for progress updates (legacy).
        phased_progress: Optional PhasedProgressCallback for multi-stage display.
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
            phased_progress,
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
    phased_progress=None,
    collections_path: Optional[str] = None,
    caches_path: Optional[str] = None,
):
    # Resolve paths
    resolved_collections_path = collections_path or str(get_default_collections_path())
    resolved_caches_path = caches_path or str(get_default_caches_path())

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
        phased_progress=phased_progress,
    )
