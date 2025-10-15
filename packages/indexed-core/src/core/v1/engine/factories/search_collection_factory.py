from core.v1.engine.persisters.disk_persister import DiskPersister
from core.v1.engine.indexes.indexer_factory import load_indexer
from core.v1.engine.core.documents_collection_searcher import DocumentCollectionSearcher

from utils.performance import log_execution_duration


def create_collection_searcher(collection_name, index_name):
    return log_execution_duration(
        lambda: __create_collection_searcher(collection_name, index_name),
        identifier="Preparing collection searcher",
    )


def __create_collection_searcher(collection_name, index_name):
    disk_persister = DiskPersister(base_path="./data/collections")

    indexer = load_indexer(index_name, collection_name, disk_persister)

    return DocumentCollectionSearcher(
        collection_name=collection_name, indexer=indexer, persister=disk_persister
    )
