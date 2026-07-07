from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

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

    @property
    def max_seq_length(self) -> int:
        """The model's real token window — the single source of truth chunkers
        must size against (bug A4). 256 for the default all-MiniLM-L6-v2."""
        return int(self.model.max_seq_length)

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
        if not texts:
            if progress_callback is not None:
                import numpy as _np

                return _np.vstack([])
            empty_result: np.ndarray = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            return empty_result

        max_len = self.max_seq_length
        tokenizer = self.model.tokenizer
        token_lengths = [
            len(tokenizer.encode(text, add_special_tokens=False)) for text in texts
        ]

        if all(length <= max_len for length in token_lengths):
            # Fast path: nothing exceeds the model window, encode as one
            # (or batched) call same as before.
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

            fast_path_result: np.ndarray = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            return fast_path_result

        # At least one text exceeds the model window (bug A4): the model
        # would otherwise silently truncate at `max_len`, so any two texts
        # sharing a window-sized prefix embed identically. Embed per item,
        # splitting over-window texts into windows and mean-pooling instead.
        import numpy as _np

        vectors = []
        for text, length in zip(texts, token_lengths):
            if length <= max_len:
                vectors.append(
                    self.model.encode(
                        text, show_progress_bar=False, convert_to_numpy=True
                    )
                )
            else:
                vectors.append(self._embed_over_window(text, tokenizer, max_len))
            if progress_callback is not None:
                progress_callback(1)

        return _np.vstack(vectors)

    def _embed_over_window(self, text: str, tokenizer: Any, max_len: int) -> np.ndarray:
        """Embed *text* exceeding the model window.

        Splits into non-overlapping ``max_len``-token windows, embeds each,
        and mean-pools (then renormalizes) into a single vector — so content
        past the window still contributes, instead of being silently dropped.
        """
        import numpy as _np

        token_ids = tokenizer.encode(text, add_special_tokens=False)
        windows = [
            tokenizer.decode(token_ids[i : i + max_len])
            for i in range(0, len(token_ids), max_len)
        ]
        window_vectors: np.ndarray = self.model.encode(
            windows, show_progress_bar=False, convert_to_numpy=True
        )
        pooled: np.ndarray = window_vectors.mean(axis=0)
        norm = _np.linalg.norm(pooled)
        result: np.ndarray = pooled / norm if norm > 0 else pooled
        return result

    def get_number_of_dimensions(self):
        return self.model.get_sentence_embedding_dimension()
