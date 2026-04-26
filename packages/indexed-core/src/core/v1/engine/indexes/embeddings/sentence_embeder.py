from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    import numpy as np

from core.v1.engine.indexes.embeddings._model_cache import get_embedding_model

# Default batch size (128 is optimal for most CPU configurations)
DEFAULT_EMBEDDING_BATCH_SIZE = 128


class SentenceEmbedder:
    def __init__(self, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name

    @property
    def model(self):
        """Lazy-load the embedding model on first access."""
        return get_embedding_model(self.model_name)

    def embed(self, text):
        return self.model.encode(text)

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> np.ndarray:
        """Encode a list of texts in one batched call for efficiency.

        Args:
            texts: List of text strings to encode.
            batch_size: Number of texts to encode per internal batch.
                Defaults to 128 (optimal for most CPU configurations).
            progress_callback: Called with the number of texts encoded after
                each internal batch, enabling external progress tracking.

        Returns:
            numpy array of embeddings with shape (len(texts), embedding_dim).
        """
        if progress_callback is not None:
            import numpy as _np

            all_embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                emb = self.model.encode(
                    batch,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
                all_embeddings.append(emb)
                progress_callback(len(batch))
            return _np.vstack(all_embeddings)

        return self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

    def get_number_of_dimensions(self):
        return self.model.get_sentence_embedding_dimension()
