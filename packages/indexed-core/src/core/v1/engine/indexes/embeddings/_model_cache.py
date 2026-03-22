"""Lazy singleton cache for embedding models.

Delegates to model_manager.load_model() which handles HF cache detection,
offline loading, and lru_cache for process-lifetime caching.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


def get_embedding_model(
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> SentenceTransformer:
    """Load embedding model lazily on first use. Cached for process lifetime."""
    from core.v1.engine.indexes.embeddings.model_manager import load_model

    return load_model(model_name)
