"""Embedding service using sentence-transformers."""

import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates embeddings using sentence-transformers.

    This service wraps a sentence-transformers model and provides
    convenient methods for embedding text with batching support.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: Optional[str] = None,
        batch_size: int = 32,
    ):
        """Initialize embedding service.

        Args:
            model_name: Name of sentence-transformers model.
            device: Device to use ("cpu", "cuda", "mps"). None = auto-detect.
            batch_size: Batch size for encoding.
        """
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name, device=device)
        self.model_name = model_name
        self.batch_size = batch_size
        logger.info(
            f"Model loaded successfully. Dimension: {self.dimension}, Device: {self.model.device}"
        )

    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector of shape (dimension,).
        """
        return self.model.encode(text, convert_to_numpy=True, show_progress_bar=False)

    def embed_batch(self, texts: List[str], show_progress: bool = True) -> np.ndarray:
        """Embed multiple texts efficiently.

        Args:
            texts: List of texts to embed.
            show_progress: Whether to show progress bar for large batches.

        Returns:
            Array of embeddings of shape (len(texts), dimension).
        """
        if not texts:
            return np.array([]).reshape(0, self.dimension)

        return self.model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            show_progress_bar=show_progress and len(texts) > 100,
        )

    @property
    def dimension(self) -> int:
        """Return embedding dimension.

        Returns:
            Dimension of embedding vectors.
        """
        return self.model.get_sentence_embedding_dimension()
