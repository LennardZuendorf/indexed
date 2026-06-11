"""Shared configuration resolution for MCP tools and resources.

Config and engine selection are loaded ONCE in the server lifespan and stored
in lifespan state. Tools and resources read them through the single
:func:`get_lifespan_value` helper — there is no global/module fallback and no
duplicated per-call config-loading blocks.
"""

from __future__ import annotations

from typing import Any, Optional


def get_lifespan_value(ctx: Optional[Any], key: str, default: Any) -> Any:
    """Return a value stored in the server lifespan state.

    This is the SINGLE config-resolution path for MCP tools and resources.
    Configuration (``mcp_config``, ``search_config``) and the active ``engine``
    are populated once by the server lifespan; this helper reads them back from
    the request context. When ``ctx`` is missing or carries no lifespan state
    (e.g., during unit tests), the supplied ``default`` is returned.

    Args:
        ctx: FastMCP request context (or ``None``).
        key: Lifespan-state key to read.
        default: Value returned when the key is unavailable.

    Returns:
        The lifespan-state value for ``key`` or ``default``.
    """
    if ctx is not None:
        try:
            lifespan_state = getattr(ctx, "lifespan_context", None)
            if lifespan_state and key in lifespan_state:
                return lifespan_state[key]
        except (AttributeError, TypeError):
            pass
    return default


def resolve_engine_for_collection(
    collection: str,
    ctx: Optional[Any],
    default_engine: str,
) -> str:
    """Resolve the engine for a collection-scoped MCP call.

    Auto-detects the engine from the collection's on-disk ``manifest.json``
    and falls back to the lifespan-cached engine default when no manifest is
    found.

    Args:
        collection: Target collection name (must be supplied for detection).
        ctx: FastMCP request context (for lifespan-cached engine default).
        default_engine: Engine used when neither manifest detection nor
            lifespan state yields a value.

    Returns:
        ``"v1"`` or ``"v2"``.
    """
    from indexed_config.errors import IndexedError

    from ..services.engine_router import detect_collection_engine
    from ..utils.storage_info import resolve_preferred_collections_path

    if collection:
        try:
            preferred_path = str(resolve_preferred_collections_path())
            detected = detect_collection_engine(collection, preferred_path)
            if detected is not None:
                return detected
        except (IndexedError, OSError):
            pass

    return str(get_lifespan_value(ctx, "engine", default_engine))
