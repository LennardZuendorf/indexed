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
from .core_config import Config  # Keep for backward compatibility

# Register core v1 config specs (lazy, best-effort)
try:
    from indexed_config import ConfigService
    from .config.models import (
        IndexingConfig,
        SearchConfig,
        VectorStoreConfig,
        EmbeddingConfig,
        ConnectorConfig,
    )

    _svc = ConfigService.instance()
    _svc.register(IndexingConfig, path="core.v1.indexing")
    _svc.register(SearchConfig, path="core.v1.search")
    _svc.register(VectorStoreConfig, path="core.v1.vector_store")
    _svc.register(EmbeddingConfig, path="core.v1.embedding")
    _svc.register(ConnectorConfig, path="core.v1.connectors")
except Exception:
    # Do not hard-fail if config package isn't available or during build
    pass

# Semantic version of the core v1 API. Used for connector compatibility checks.
__version__ = "1.0.0"

__all__ = ["Index", "IndexConfig", "Config", "__version__"]
