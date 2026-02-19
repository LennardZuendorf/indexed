"""Configuration models for core.v1 components.

These models define the configuration schema for indexing, embedding,
storage, search, and infrastructure settings.
"""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CoreV1IndexingConfig(BaseModel):
    """Indexing pipeline configuration for core.v1."""

    chunk_size: int = Field(
        default=512, ge=1, le=4096, description="Size of text chunks for indexing"
    )
    chunk_overlap: int = Field(
        default=50, ge=0, description="Overlap between consecutive chunks"
    )
    batch_size: int = Field(
        default=32, ge=1, description="Batch size for processing documents"
    )

    @field_validator("chunk_overlap")
    @classmethod
    def validate_overlap(cls, v: int, info) -> int:
        """Ensure overlap is less than chunk size."""
        if "chunk_size" in info.data and v >= info.data["chunk_size"]:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return v


class CoreV1EmbeddingConfig(BaseModel):
    """Embedding generation configuration for core.v1."""

    provider: str = Field(
        default="sentence-transformers",
        description="Embedding provider (sentence-transformers, openai, voyage)",
    )
    model_name: str = Field(
        default="all-MiniLM-L6-v2",
        description="Model name for embeddings",
    )
    dimension: Optional[int] = Field(
        default=None, description="Embedding dimension (auto-detected if None)"
    )
    batch_size: int = Field(
        default=64, ge=1, description="Batch size for embedding generation"
    )
    device: Optional[str] = Field(
        default=None,
        description="Device for embeddings (cpu, cuda, mps, or None for auto)",
    )
    api_key_env: Optional[str] = Field(
        default=None, description="Environment variable name for API key (if needed)"
    )


class CoreV1StorageConfig(BaseModel):
    """Vector storage configuration for core.v1."""

    type: str = Field(default="faiss", description="Storage backend type")
    index_type: str = Field(default="IndexFlatL2", description="FAISS index type")
    persistence_enabled: bool = Field(
        default=True, description="Enable persistence to disk"
    )
    persistence_path: Optional[Path] = Field(
        default=None, description="Path for persisting indexes"
    )

    @field_validator("persistence_path", mode="before")
    @classmethod
    def set_default_path(cls, v, info) -> Optional[Path]:
        """Set default persistence path if not provided."""
        if v is None:
            return Path(".indexed/v1/storage")
        return Path(v) if isinstance(v, str) else v


class CoreV1SearchConfig(BaseModel):
    """Search configuration for core.v1.

    Default values are optimized for LLM consumption via MCP:
    - include_matched_chunks=True ensures text content is returned
    - max_docs=10 and max_chunks=30 provide comprehensive results
    """

    max_docs: int = Field(
        default=10, ge=1, le=100, description="Maximum documents to return"
    )
    max_chunks: Optional[int] = Field(
        default=30, ge=1, description="Maximum chunks to return"
    )
    include_full_text: bool = Field(
        default=False, description="Include full document text in results"
    )
    include_all_chunks: bool = Field(
        default=False, description="Include all document chunks"
    )
    include_matched_chunks: bool = Field(
        default=True,
        description="Include matched chunk content (required for LLM usage)",
    )
    score_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Minimum similarity score threshold"
    )


def get_default_collections_path() -> Path:
    """Get default collections path from storage config."""
    try:
        from indexed_config import get_resolver

        resolver = get_resolver()
        return resolver.get_collections_path()
    except ImportError:
        return Path.home() / ".indexed" / "data" / "collections"


def get_default_caches_path() -> Path:
    """Get default caches path from storage config."""
    try:
        from indexed_config import get_resolver

        resolver = get_resolver()
        return resolver.get_caches_path()
    except ImportError:
        return Path.home() / ".indexed" / "data" / "caches"


class PathsConfig(BaseModel):
    """File system paths configuration.

    Paths default to the global storage location (~/.indexed/data/...)
    unless explicitly configured otherwise.
    """

    collections_dir: Path = Field(
        default_factory=get_default_collections_path,
        description="Directory for collections storage",
    )
    caches_dir: Path = Field(
        default_factory=get_default_caches_path,
        description="Directory for document caches",
    )
    temp_dir: Path = Field(
        default=Path("./tmp"), description="Temporary files directory"
    )

    @field_validator("collections_dir", "caches_dir", "temp_dir", mode="before")
    @classmethod
    def ensure_path(cls, v) -> Path:
        """Convert string to Path and ensure directory exists."""
        path = Path(v) if isinstance(v, str) else v
        path.mkdir(parents=True, exist_ok=True)
        return path


class MCPConfig(BaseModel):
    """MCP server configuration."""

    host: str = Field(default="localhost", description="MCP server host")
    port: int = Field(default=8000, ge=1, le=65535, description="MCP server port")
    log_level: str = Field(
        default="WARNING",
        description="MCP server log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    enable_async_pool: bool = Field(
        default=False, description="Enable async processing pool"
    )
    include_index_size: bool = Field(
        default=False, description="Include index size in MCP responses"
    )


class PerformanceConfig(BaseModel):
    """Performance and caching configuration."""

    enable_cache: bool = Field(default=True, description="Enable search result caching")
    cache_max_entries: int = Field(
        default=32, ge=1, description="Maximum cache entries"
    )
    log_sqlite_queries: bool = Field(
        default=False, description="Log SQLite queries for debugging"
    )


class LoggingConfig(BaseModel):
    """Central logging configuration."""

    level: str = Field(
        default="WARNING",
        description="Global log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    as_json: bool = Field(default=False, description="Emit JSON-formatted logs")


__all__ = [
    "CoreV1IndexingConfig",
    "CoreV1EmbeddingConfig",
    "CoreV1StorageConfig",
    "CoreV1SearchConfig",
    "PathsConfig",
    "MCPConfig",
    "PerformanceConfig",
    "LoggingConfig",
    "get_default_collections_path",
    "get_default_caches_path",
]
