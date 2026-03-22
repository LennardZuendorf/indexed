from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

from core.v1.engine.indexes.embeddings._model_cache import get_embedding_model


class SentenceEmbedder:
    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name

    @property
    def model(self):
        """Lazy-load the embedding model on first access."""
        return get_embedding_model(self.model_name)

    def embed(self, text):
        return self.model.encode(text)

    def embed_batch(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """Encode a list of texts in one batched call for efficiency.

        Args:
            texts: List of text strings to encode.
            batch_size: Number of texts to encode per internal batch.

        Returns:
            numpy array of embeddings with shape (len(texts), embedding_dim).
        """
        return self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 100,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

    def get_number_of_dimensions(self):
        return self.model.get_sentence_embedding_dimension()
