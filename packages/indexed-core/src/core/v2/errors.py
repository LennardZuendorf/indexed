"""Exception hierarchy for core v2.

All exceptions inherit from IndexedError (defined in indexed-config)
so CLI and MCP layers can catch them at a single point.
"""

from __future__ import annotations

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
