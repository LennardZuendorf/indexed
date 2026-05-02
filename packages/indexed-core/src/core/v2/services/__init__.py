"""V2 service layer — orchestration between CLI/MCP and domain modules."""

from .collection_service import clear, create, update
from .inspect_service import inspect, status
from .models import CollectionInfo, CollectionStatus, SearchResult, SourceConfig
from .search_service import SearchService, search

__all__ = [
    "CollectionInfo",
    "CollectionStatus",
    "SearchResult",
    "SearchService",
    "SourceConfig",
    "clear",
    "create",
    "inspect",
    "search",
    "status",
    "update",
]
