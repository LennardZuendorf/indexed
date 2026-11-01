"""Config models for core.v2 components (core-v2/2a, +2/6 rerank).

Pure pydantic — no LlamaIndex import. tech.md §"Config" defines
``[core.v2.embedding]``, ``[core.v2.search]`` and ``[core.v2.rerank]``: there is
intentionally NO ``[core.v2.storage]`` model (the manifest's ``vectorStore``
field is the seam — a config knob arrives with the second store, no phantom
generality). ``[core.v2.rerank]`` is disabled by default (R10): when off, no
``SentenceTransformerRerank``/``CrossEncoder`` is imported or loaded — enabling
it downloads the cross-encoder model on first use (opt-in, unlike the
default-local embedding path).
"""

from pydantic import BaseModel, Field


class CoreV2EmbeddingConfig(BaseModel):
    """Embedding configuration for core.v2 — 1:1 parity with v1's model."""

    model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="HuggingFace model name for embeddings (matches v1)",
    )
    batch_size: int = Field(
        default=32, ge=1, description="Batch size for embedding generation"
    )


class CoreV2SearchConfig(BaseModel):
    """Search configuration for core.v2."""

    max_docs: int = Field(default=10, ge=1, description="Maximum documents to return")
    score_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity to keep a result; 0 disables",
    )


class CoreV2RerankConfig(BaseModel):
    """Optional reranking configuration for core.v2 (R10) — off by default.

    When ``enabled`` is False the search path constructs no
    ``SentenceTransformerRerank`` and imports no ``CrossEncoder`` (zero cost).
    When True, the cross-encoder ``model`` reranks the retrieved nodes and keeps
    the ``top_n`` best.
    """

    enabled: bool = Field(
        default=False,
        description="Enable cross-encoder reranking of v2 search results",
    )
    model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Cross-encoder model for reranking (downloaded on first use)",
    )
    top_n: int = Field(
        default=10, ge=1, description="Number of top results to keep after reranking"
    )


__all__ = ["CoreV2EmbeddingConfig", "CoreV2SearchConfig", "CoreV2RerankConfig"]
