import numpy as np


class FaissIndexer:
    def __init__(self, name, embedder, serialized_index=None, faiss_index=None):
        self.name = name
        self.embedder = embedder

        if faiss_index is not None:
            # Pre-loaded index (e.g., via memory-mapped read_index)
            self.faiss_index = faiss_index
        elif serialized_index is not None:
            import faiss

            self.faiss_index = faiss.deserialize_index(serialized_index)
        else:
            import faiss

            self.faiss_index = faiss.IndexIDMap(
                faiss.IndexFlatL2(embedder.get_number_of_dimensions())
            )

    def get_name(self):
        return self.name

    def index_texts(self, ids, texts):
        embeddings = self.embedder.embed_batch(texts, batch_size=64)
        self.faiss_index.add_with_ids(embeddings, np.array(ids, dtype=np.int64))

    def remove_ids(self, ids):
        self.faiss_index.remove_ids(ids)

    def serialize(self):
        import faiss

        return faiss.serialize_index(self.faiss_index)

    def get_faiss_index(self):
        """Return the underlying FAISS index for direct persistence."""
        return self.faiss_index

    def search(self, text, number_of_results=10):
        return self.faiss_index.search(
            np.expand_dims(self.embedder.embed(text), axis=0), number_of_results
        )

    def get_size(self):
        return self.faiss_index.ntotal
