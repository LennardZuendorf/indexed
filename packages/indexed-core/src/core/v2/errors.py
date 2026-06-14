"""Exception hierarchy for core v2.

All exceptions inherit from IndexedError (defined in indexed-config)
so CLI and MCP layers can catch them at a single point.
"""

from __future__ import annotations

from typing import Optional

from indexed_config.errors import IndexedError


class CoreV2Error(IndexedError):
    """Base exception for all core v2 errors."""


class CollectionNotFoundError(CoreV2Error):
    """Raised when a requested collection does not exist."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Collection '{name}' not found")


class IngestionError(CoreV2Error):
    """Raised when document ingestion fails."""


class EmbeddingError(CoreV2Error):
    """Raised when embedding generation fails."""


class VectorStoreError(CoreV2Error):
    """Raised when vector store operations fail."""


class CollectionEngineMismatchError(VectorStoreError):
    """Raised when a collection exists on disk but isn't a usable v2 store.

    The common case is a v1 (legacy FAISS) collection being read by the v2
    engine. Carries the collection name and the detected on-disk engine so
    callers can surface an actionable suggestion instead of leaking LlamaIndex
    internals. Subclasses :class:`VectorStoreError` so existing
    ``except IndexedError`` / ``except VectorStoreError`` handlers still catch it.
    """

    def __init__(self, name: str, detected_engine: Optional[str] = None) -> None:
        self.name = name
        self.detected_engine = detected_engine
        if detected_engine == "v1":
            message = (
                f"Collection '{name}' is a v1 collection, not a v2 store. "
                "Search it without --engine, pass --engine v1, or rebuild it "
                "with --engine v2."
            )
        else:
            message = (
                f"Collection '{name}' is not a usable v2 store "
                "(missing LlamaIndex index files). Rebuild it with --engine v2."
            )
        super().__init__(message)
