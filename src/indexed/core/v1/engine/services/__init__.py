"""Services package for indexed application."""

from .collection_service import clear, collection_exists, create, update
from .inspect_service import InspectService, inspect, status
from .models import (
    CollectionInfo,
    CollectionStatus,
    PhasedProgressCallback,
    SourceConfig,
)
from .search_service import SearchService, search

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
