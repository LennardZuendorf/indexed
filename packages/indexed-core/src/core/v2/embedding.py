"""HuggingFace ONNX embedding wrapper for LlamaIndex.

Provides lazy-loaded embedding models with process-lifetime caching.
The ONNX backend is preferred for faster inference, with PyTorch fallback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .errors import EmbeddingError

if TYPE_CHECKING:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

_cached_model: Optional["HuggingFaceEmbedding"] = None
_cached_model_name: Optional[str] = None


def get_embed_model(
    model_name: str = "all-MiniLM-L6-v2",
) -> "HuggingFaceEmbedding":
    """Return a HuggingFace embedding model, lazily loaded and cached.

    The model is cached for the process lifetime. Subsequent calls with
    the same ``model_name`` return the cached instance.

    Args:
        model_name: HuggingFace model name (e.g. ``all-MiniLM-L6-v2``).
            If no ``/`` is present, ``sentence-transformers/`` is prepended.

    Returns:
        A :class:`HuggingFaceEmbedding` instance usable by LlamaIndex.

    Raises:
        EmbeddingError: If the model cannot be loaded.
    """
    global _cached_model, _cached_model_name  # noqa: PLW0603

    if _cached_model is not None and _cached_model_name == model_name:
        return _cached_model

    repo_id = (
        f"sentence-transformers/{model_name}" if "/" not in model_name else model_name
    )

    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    except ImportError as exc:
        msg = (
            "llama-index-embeddings-huggingface is required for v2. "
            "Install it with: uv add llama-index-embeddings-huggingface"
        )
        raise EmbeddingError(msg) from exc

    try:
        _cached_model = HuggingFaceEmbedding(model_name=repo_id)
        _cached_model_name = model_name
    except Exception as exc:
        msg = f"Failed to load embedding model '{repo_id}': {exc}"
        raise EmbeddingError(msg) from exc

    return _cached_model


def reset_cache() -> None:
    """Clear the cached embedding model. Useful for testing."""
    global _cached_model, _cached_model_name  # noqa: PLW0603
    _cached_model = None
    _cached_model_name = None
