# Public interfaces for the services layer
from .models import SourceConfig, CollectionStatus

# Collection service (functional interface only)
from .collection_service import create, update, clear

# Search service (both functional and class interfaces)
from .search_service import search, SearchService

# Inspect service (both functional and class interfaces)
from .inspect_service import status, InspectService

__all__ = [
    # Models
    "SourceConfig",
    "CollectionStatus",
    # Collection service functions
    "create",
    "update",
    "clear",
    # Search service
    "search",
    "SearchService",
    # Inspect service
    "status",
    "InspectService",
]
