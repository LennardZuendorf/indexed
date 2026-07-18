"""Core engine facade — the single surface the app (CLI/MCP) calls (R2).

The app imports collection/search/inspect operations and the shared models from
``core.v1.engine``; it never reaches into ``core.v1.engine.services`` /
``factories`` / ``core`` directly. A v2 engine ships as a new implementation
behind these same names over the same on-disk format — nothing above the facade
changes (the core-swap seam).

Resolution is lazy (module ``__getattr__``): importing ``core.v1.engine`` stays
cheap, and the first facade access warms the services package in the correct
order (avoiding the cold-import cycle documented in ``.spec/lessons.md``).
"""

from typing import TYPE_CHECKING, Any

_EXPORTS = frozenset(
    {
        # models
        "SourceConfig",
        "CollectionStatus",
        "CollectionInfo",
        "PhasedProgressCallback",
        # collection operations
        "create",
        "update",
        "clear",
        "collection_exists",
        # search operations
        "search",
        "SearchService",
        # inspect operations
        "status",
        "inspect",
        "InspectService",
    }
)


def __getattr__(name: str) -> Any:
    if name in _EXPORTS:
        from indexed.core.v1.engine import services

        return getattr(services, name)
    raise AttributeError(f"module 'indexed.core.v1.engine' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_EXPORTS)


if TYPE_CHECKING:  # help type-checkers/IDEs see the re-exported names
    from indexed.core.v1.engine.services import (  # noqa: F401
        CollectionInfo,
        CollectionStatus,
        InspectService,
        PhasedProgressCallback,
        SearchService,
        SourceConfig,
        clear,
        collection_exists,
        create,
        inspect,
        search,
        status,
        update,
    )


__all__ = sorted(_EXPORTS)
