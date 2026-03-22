"""FAISS indexer with automatic index type selection based on collection size.

Selects the optimal FAISS index type:
- < 10,000 vectors: IndexFlatL2 (exact, fast enough)
- 10,000 - 1,000,000: IndexHNSWFlat (approximate, very fast, ~98% recall)
- > 1,000,000: IndexIVFPQ (approximate, memory-efficient)
"""

import numpy as np


def _create_faiss_index(dimension: int, num_vectors: int = 0):
    """Select optimal FAISS index type based on expected collection size."""
    import faiss

    if num_vectors < 10_000:
        return faiss.IndexFlatL2(dimension)

    if num_vectors < 1_000_000:
        index = faiss.IndexHNSWFlat(dimension, 32)
        index.hnsw.efConstruction = 200
        index.hnsw.efSearch = 128
        return index

    # Large scale: IVF with Product Quantization
    nlist = min(int(np.sqrt(num_vectors)), 4096)
    quantizer = faiss.IndexFlatL2(dimension)
    index = faiss.IndexIVFPQ(
        quantizer,
        dimension,
        nlist,
        16,
        8,
    )
    return index


def _set_search_params(index):
    """Set optimal search parameters for loaded indexes."""
    if hasattr(index, "hnsw"):
        index.hnsw.efSearch = 128


class FaissAutoIndexer:
    """FAISS indexer that auto-selects the best index type based on data size.

    For new collections, call `build_index(ids, texts)` to create an optimized
    index. For loaded collections, the existing index type is preserved.
    """

    def __init__(self, name, embedder, serialized_index=None):
        import faiss

        self.name = name
        self.embedder = embedder
        if serialized_index is not None:
            self.faiss_index = faiss.deserialize_index(serialized_index)
            _set_search_params(self.faiss_index)
        else:
            # Defer index creation until we know the data size
            self.faiss_index = None
            self._dimension = embedder.get_number_of_dimensions()

    def get_name(self):
        return self.name

    def index_texts(self, ids, texts):
        import faiss

        embeddings = self.embedder.embed_batch(texts, batch_size=64)

        if self.faiss_index is None:
            num_vectors = len(ids)
            inner_index = _create_faiss_index(self._dimension, num_vectors)

            # IVF indexes require training
            if hasattr(inner_index, "train"):
                if not inner_index.is_trained:
                    inner_index.train(embeddings)

            self.faiss_index = faiss.IndexIDMap(inner_index)

        self.faiss_index.add_with_ids(embeddings, np.array(ids, dtype=np.int64))

    def remove_ids(self, ids):
        self.faiss_index.remove_ids(ids)

    def serialize(self):
        import faiss

        return faiss.serialize_index(self.faiss_index)

    def search(self, text, number_of_results=10):
        return self.faiss_index.search(
            np.expand_dims(self.embedder.embed(text), axis=0), number_of_results
        )

    def get_size(self):
        return self.faiss_index.ntotal
