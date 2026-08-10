from collections.abc import Callable
from typing import Any

from indexed.config.errors import missing_wiring_error
from indexed.core.v1.config_models import (
    get_default_caches_path,
    get_default_collections_path,
)
from indexed.core.v1.engine.core.documents_collection_creator import (
    OPERATION_TYPE,
    DocumentCollectionCreator,
)
from indexed.core.v1.engine.indexes.indexer_factory import create_indexer
from indexed.core.v1.engine.persisters.disk_persister import DiskPersister
from indexed.protocols import PhasedProgressCallback
from indexed.utils.performance import log_execution_duration


def create_collection_creator(
    collection_name,
    indexers,
    document_reader,
    document_converter,
    use_cache=True,
    phased_progress: PhasedProgressCallback | None = None,
    collections_path: str | None = None,
    caches_path: str | None = None,
    cache_decorator_factory: Callable[[Any, DiskPersister], Any] | None = None,
):
    """Create a collection creator instance."""
    return log_execution_duration(
        lambda: __create_collection_creator(
            collection_name,
            indexers,
            document_reader,
            document_converter,
            use_cache,
            phased_progress,
            collections_path,
            caches_path,
            cache_decorator_factory,
        ),
        identifier="Preparing collection creator",
    )


def __create_collection_creator(
    collection_name,
    indexers,
    document_reader,
    document_converter,
    use_cache,
    phased_progress: PhasedProgressCallback | None = None,
    collections_path: str | None = None,
    caches_path: str | None = None,
    cache_decorator_factory: Callable[[Any, DiskPersister], Any] | None = None,
):
    resolved_collections_path = collections_path or str(get_default_collections_path())
    resolved_caches_path = caches_path or str(get_default_caches_path())

    if use_cache:
        if cache_decorator_factory is None:
            raise missing_wiring_error(
                "cache_decorator_factory (required when use_cache=True)"
            )
        cache_disk_persister = DiskPersister(base_path=resolved_caches_path)
        result_document_reader = cache_decorator_factory(
            document_reader, cache_disk_persister
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
        phased_progress=phased_progress,
    )
