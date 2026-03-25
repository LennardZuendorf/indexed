"""Services package for indexed application."""

from .models import (
    SourceConfig,
    CollectionStatus,
    SearchResult,
    CollectionInfo,
    ProgressUpdate,
    ProgressCallback,
    PhasedProgressCallback,
)
from .collection_service import create, update, clear
from .search_service import search, SearchService
from .inspect_service import status, inspect, InspectService

__all__ = [
    # Models
    "SourceConfig",
    "CollectionStatus",
    "CollectionInfo",
    "SearchResult",
    "ProgressUpdate",
    "ProgressCallback",
    "PhasedProgressCallback",
    # Collection operations
    "create",
    "update",
    "clear",
    # Search operations
    "search",
    "SearchService",
    # Inspect operations
    "status",
    "inspect",
    "InspectService",
]
