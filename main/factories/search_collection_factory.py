from main.persisters.disk_persister import DiskPersister
from main.indexes.indexer_factory import load_indexer
from main.core.documents_collection_searcher import DocumentCollectionSearcher

def create_collection_searcher(collection_name, index_name):
    disk_persister = DiskPersister(base_path="./data/collections")

    indexer = load_indexer(index_name, collection_name, disk_persister)
    
    return DocumentCollectionSearcher(collection_name=collection_name, 
                                      indexer=indexer, 
                                      persister=disk_persister)
