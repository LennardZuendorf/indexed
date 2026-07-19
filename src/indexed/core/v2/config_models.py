"""Config models for core.v2 components (core-v2/2a).

Pure pydantic — no LlamaIndex import. tech.md §"Config" defines
``[core.v2.embedding]`` and ``[core.v2.search]`` only: there is intentionally
NO ``[core.v2.storage]`` model (the manifest's ``vectorStore`` field is the
seam — a config knob arrives with the second store, no phantom generality)
and NO ``[core.v2.rerank]`` model (that lands in core-v2/6).
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


__all__ = ["CoreV2EmbeddingConfig", "CoreV2SearchConfig"]
