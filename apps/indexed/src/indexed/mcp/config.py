"""Shared configuration resolution for MCP tools and resources."""

from typing import Any, Callable, Optional


def resolve_config(ctx: Optional[Any], key: str, loader: Callable[[], Any]) -> Any:
    """Resolve config from lifespan state or fallback to loader."""
    if ctx is not None:
        try:
            lifespan_state = getattr(ctx, "lifespan_context", None)
            if lifespan_state and key in lifespan_state:
                return lifespan_state[key]
        except (AttributeError, TypeError):
            pass
    return loader()


def resolve_engine_for_collection(
    collection: str,
    ctx: Optional[Any],
    fallback_loader: Callable[[], str],
) -> str:
    """Resolve the engine for a collection-scoped MCP call.

    Auto-detects the engine from the collection's on-disk ``manifest.json``
    and falls back to the lifespan-cached config default (or the loader)
    when no manifest is found.

    Args:
        collection: Target collection name (must be supplied for detection).
        ctx: FastMCP request context (for lifespan-cached config default).
        fallback_loader: Callable returning the config default engine when
            ``ctx`` has no lifespan state.

    Returns:
        ``"v1"`` or ``"v2"``.
    """
    from ..services.engine_router import detect_collection_engine
    from ..utils.storage_info import resolve_preferred_collections_path

    if collection:
        try:
            preferred_path = str(resolve_preferred_collections_path())
            detected = detect_collection_engine(collection, preferred_path)
            if detected is not None:
                return detected
        except Exception:
            pass

    return str(resolve_config(ctx, "engine", fallback_loader))
