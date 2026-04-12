"""Indexed v1 API - Simple, clean interface for document search.

Provides high-level Index and IndexConfig classes for managing document
collections and performing semantic search.

Examples:
    >>> from core.v1 import Index, IndexConfig
    >>>
    >>> index = Index()
    >>> index.add_collection("docs", connector="filesystem", path="./docs")
    >>> results = index.search("authentication methods")
"""

from .index import Index, IndexConfig

# Register core v1 config specs (lazy, best-effort)
try:
    from indexed_config import ConfigService
    from .config_models import (
        CoreV1IndexingConfig,
        CoreV1SearchConfig,
        CoreV1StorageConfig,
        CoreV1EmbeddingConfig,
    )

    _svc = ConfigService.instance()
    _svc.register(CoreV1IndexingConfig, path="core.v1.indexing")
    _svc.register(CoreV1SearchConfig, path="core.v1.search")
    _svc.register(CoreV1StorageConfig, path="core.v1.vector_store")
    _svc.register(CoreV1EmbeddingConfig, path="core.v1.embedding")
except Exception:
    # Do not hard-fail if config package isn't available or during build
    pass

# Semantic version of the core v1 API. Used for connector compatibility checks.
__version__ = "1.0.0"

__all__ = ["Index", "IndexConfig", "__version__"]
