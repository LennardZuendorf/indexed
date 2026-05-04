"""V2 service layer — orchestration between CLI/MCP and domain modules.

Re-exports are lazy: importing this module does not pull in the heavy
LlamaIndex / HuggingFace stack. Symbols resolve on first attribute access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import (
        CollectionInfo,
        CollectionStatus,
        SearchResult,
        SourceConfig,
    )
    from .search_service import SearchService

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

_SOURCES = {
    "clear": ("collection_service", "clear"),
    "create": ("collection_service", "create"),
    "update": ("collection_service", "update"),
    "inspect": ("inspect_service", "inspect"),
    "status": ("inspect_service", "status"),
    "SearchService": ("search_service", "SearchService"),
    "search": ("search_service", "search"),
    "CollectionInfo": ("models", "CollectionInfo"),
    "CollectionStatus": ("models", "CollectionStatus"),
    "SearchResult": ("models", "SearchResult"),
    "SourceConfig": ("models", "SourceConfig"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _SOURCES[name]
    except KeyError as exc:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
    from importlib import import_module

    module = import_module(f"{__name__}.{module_name}")
    return getattr(module, attr_name)
