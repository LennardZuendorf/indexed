import numpy as np


def _resolve_embedding_batch_size() -> int:
    """Read the registered ``[core.v1.embedding] batch_size`` (foundation/6
    E12: the indexer used to hardcode 64, ignoring the registered config
    default of 128). Falls back to the embedder's own default when the
    section isn't registered/set — e.g. in isolated unit tests or callers
    that never wired ``register_app_config``.
    """
    from core.v1.engine.indexes.embeddings.sentence_embeder import (
        DEFAULT_EMBEDDING_BATCH_SIZE,
    )

    try:
        from core.v1.config_models import CoreV1EmbeddingConfig
        from indexed_config import ConfigService

        provider = ConfigService.instance().bind()
        return provider.get(CoreV1EmbeddingConfig).batch_size
    except Exception:
        return DEFAULT_EMBEDDING_BATCH_SIZE


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

    def index_texts(self, ids, texts, progress_callback=None):
        if not ids or not texts:
            # B2: a zero-chunk batch is a safe no-op (mirrors the existing
            # empty-remove_ids no-op below) instead of crashing on the
            # malformed shape an empty encode() call can produce.
            return
        embeddings = self.embedder.embed_batch(
            texts,
            batch_size=_resolve_embedding_batch_size(),
            progress_callback=progress_callback,
        )
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
