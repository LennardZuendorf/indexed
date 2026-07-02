from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from protocols.models import (
    PhasedProgressCallback,
    ProgressCallback,
    ProgressUpdate,
    SourceConfig,
)


@dataclass
class CollectionStatus:
    """Status information for a collection."""

    name: str
    number_of_documents: int
    number_of_chunks: int
    updated_time: str
    last_modified_document_time: str
    indexers: List[str]
    index_size: Optional[int] = None
    # Newly added optional metadata
    source_type: Optional[str] = None
    relative_path: Optional[str] = None
    disk_size_bytes: Optional[int] = None


@dataclass
class CollectionInfo:
    """Detailed inspection information for a collection.

    This model contains comprehensive metadata about a collection including
    document counts, storage information, timestamps, and computed statistics.
    It's designed to be presentation-layer agnostic and can be formatted for
    different output types (CLI, JSON, etc.).
    """

    # Basic identity
    name: str
    source_type: Optional[str] = None

    # Counts
    number_of_documents: int = 0
    number_of_chunks: int = 0

    # Storage
    relative_path: Optional[str] = None
    disk_size_bytes: Optional[int] = None
    index_size_bytes: Optional[int] = None

    # Timestamps
    created_time: Optional[str] = None
    updated_time: Optional[str] = None
    last_modified_document_time: Optional[str] = None

    # Index info
    indexers: List[str] = None

    # Computed statistics (calculated from other fields)
    avg_chunks_per_doc: Optional[float] = None
    avg_doc_size_bytes: Optional[float] = None

    def __post_init__(self):
        """Calculate derived statistics after initialization."""
        if self.indexers is None:
            self.indexers = []

        # Calculate averages
        if self.number_of_documents > 0:
            self.avg_chunks_per_doc = self.number_of_chunks / self.number_of_documents

            if self.disk_size_bytes:
                self.avg_doc_size_bytes = (
                    self.disk_size_bytes / self.number_of_documents
                )


@dataclass
class SearchResult:
    """A single search result from a collection."""

    id: str
    collection_name: str
    url: Optional[str] = None
    path: Optional[str] = None
    score: Optional[float] = None
    matched_chunks: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.matched_chunks is None:
            self.matched_chunks = []


# Re-export progress types from protocols during transition window.
__all__ = [
    "CollectionInfo",
    "CollectionStatus",
    "PhasedProgressCallback",
    "ProgressCallback",
    "ProgressUpdate",
    "SearchResult",
    "SourceConfig",
]
