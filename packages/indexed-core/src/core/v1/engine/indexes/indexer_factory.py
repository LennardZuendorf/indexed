from .indexers.faiss_indexer import FaissIndexer
from .embeddings.sentence_embeder import SentenceEmbedder


def create_indexer(indexer_name):
    if indexer_name == "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2":
        return FaissIndexer(
            indexer_name,
            SentenceEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2"),
        )

    if indexer_name == "indexer_FAISS_IndexFlatL2__embeddings_all-mpnet-base-v2":
        return FaissIndexer(
            indexer_name,
            SentenceEmbedder(model_name="sentence-transformers/all-mpnet-base-v2"),
        )

    if (
        indexer_name
        == "indexer_FAISS_IndexFlatL2__embeddings_multi-qa-distilbert-cos-v1"
    ):
        return FaissIndexer(
            indexer_name,
            SentenceEmbedder(
                model_name="sentence-transformers/multi-qa-distilbert-cos-v1"
            ),
        )

    raise ValueError(f"Unknown indexer name: {indexer_name}")


def load_indexer(indexer_name, collection_name, persister):
    if indexer_name == "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2":
        serialized_index = persister.read_bin_file(
            f"{collection_name}/indexes/{indexer_name}/indexer"
        )
        return FaissIndexer(
            indexer_name,
            SentenceEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2"),
            serialized_index,
        )

    if indexer_name == "indexer_FAISS_IndexFlatL2__embeddings_all-mpnet-base-v2":
        serialized_index = persister.read_bin_file(
            f"{collection_name}/indexes/{indexer_name}/indexer"
        )
        return FaissIndexer(
            indexer_name,
            SentenceEmbedder(model_name="sentence-transformers/all-mpnet-base-v2"),
            serialized_index,
        )

    if (
        indexer_name
        == "indexer_FAISS_IndexFlatL2__embeddings_multi-qa-distilbert-cos-v1"
    ):
        serialized_index = persister.read_bin_file(
            f"{collection_name}/indexes/{indexer_name}/indexer"
        )
        return FaissIndexer(
            indexer_name,
            SentenceEmbedder(
                model_name="sentence-transformers/multi-qa-distilbert-cos-v1"
            ),
            serialized_index,
        )

    raise ValueError(f"Unknown indexer name: {indexer_name}")
