"""Lazy singleton cache for embedding models.

Ensures the model is loaded exactly once per process, but only when first needed.
This avoids the 2-3 second startup cost of importing sentence_transformers/torch
for CLI commands that don't require embeddings.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=1)
def get_embedding_model(
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> SentenceTransformer:
    """Load embedding model lazily on first use. Cached for process lifetime."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)
