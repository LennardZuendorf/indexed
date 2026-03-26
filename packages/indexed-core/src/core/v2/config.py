"""Configuration models for core v2.

Pydantic models registered at the ``core.v2.*`` namespace.
Registration is explicit via :func:`register_config` — never at import time.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CoreV2EmbeddingConfig(BaseModel):
    """Embedding generation configuration."""

    model_name: str = Field(
        default="all-MiniLM-L6-v2",
        description="HuggingFace sentence-transformers model name",
    )
    batch_size: int = Field(
        default=128, ge=1, description="Batch size for embedding generation"
    )


class CoreV2IndexingConfig(BaseModel):
    """Indexing pipeline configuration."""

    chunk_size: int = Field(
        default=512, ge=1, le=4096, description="Size of text chunks"
    )
    chunk_overlap: int = Field(
        default=50, ge=0, description="Overlap between consecutive chunks"
    )
    batch_size: int = Field(
        default=32, ge=1, description="Batch size for document processing"
    )

    @field_validator("chunk_overlap")
    @classmethod
    def validate_overlap(cls, v: int, info: object) -> int:
        """Ensure overlap is less than chunk size."""
        data = getattr(info, "data", {})
        if "chunk_size" in data and v >= data["chunk_size"]:
            msg = "chunk_overlap must be less than chunk_size"
            raise ValueError(msg)
        return v


class CoreV2StorageConfig(BaseModel):
    """Vector storage configuration."""

    vector_store: str = Field(
        default="faiss",
        description="Vector store backend (faiss, chroma, qdrant)",
    )
    persistence_enabled: bool = Field(
        default=True, description="Enable persistence to disk"
    )


class CoreV2SearchConfig(BaseModel):
    """Search configuration."""

    max_docs: int = Field(
        default=10, ge=1, le=100, description="Maximum documents to return"
    )
    max_chunks: int = Field(default=30, ge=1, description="Maximum chunks to return")
    similarity_top_k: int = Field(
        default=30, ge=1, description="Top-k for LlamaIndex retriever"
    )
    include_matched_chunks: bool = Field(
        default=True, description="Include matched chunk content in results"
    )
    score_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Minimum similarity score"
    )


def register_config(config_service: object) -> None:
    """Register all v2 config specs with the ConfigService.

    Called explicitly by app startup — never at import time.
    """
    register = getattr(config_service, "register")
    register(CoreV2EmbeddingConfig, path="core.v2.embedding")
    register(CoreV2IndexingConfig, path="core.v2.indexing")
    register(CoreV2StorageConfig, path="core.v2.storage")
    register(CoreV2SearchConfig, path="core.v2.search")
