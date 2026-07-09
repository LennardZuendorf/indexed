"""Services package for indexed application."""

from .models import (
    SourceConfig,
    CollectionStatus,
    CollectionInfo,
    PhasedProgressCallback,
)
from .collection_service import create, update, clear, collection_exists
from .search_service import search, SearchService
from .inspect_service import status, inspect, InspectService

__all__ = [
    # Models
    "SourceConfig",
    "CollectionStatus",
    "CollectionInfo",
    "PhasedProgressCallback",
    # Collection operations
    "create",
    "update",
    "clear",
    "collection_exists",
    # Search operations
    "search",
    "SearchService",
    # Inspect operations
    "status",
    "inspect",
    "InspectService",
]
