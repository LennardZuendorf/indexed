"""Services package for indexed application."""

from .models import SourceConfig, CollectionStatus
from .collection_service import create, update, clear
from .search_service import search, SearchService
from .inspect_service import status, InspectService
from .config_service import ConfigService, get_config, update_config, set_config

__all__ = [
    # Models
    "SourceConfig",
    "CollectionStatus",
    
    # Collection operations
    "create",
    "update", 
    "clear",
    
    # Search operations
    "search",
    "SearchService",
    
    # Inspect operations
    "status",
    "InspectService",
    
    # Configuration operations
    "ConfigService",
    "get_config",
    "update_config", 
    "set_config",
]
