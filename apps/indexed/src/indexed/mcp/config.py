"""Shared configuration resolution for MCP tools and resources."""

from typing import Any, Callable, Optional


from indexed.composition import CliContext, resolve_collections_context

_MISSING = object()


def _from_lifespan(ctx: Optional[Any], key: str) -> Any:
    """Return the value stored at ``key`` in the FastMCP lifespan context.

    Returns _MISSING sentinel when the key is absent or the context is invalid,
    which lets callers distinguish a stored ``None`` from a missing key.
    """
    if ctx is not None:
        try:
            lifespan_state = getattr(ctx, "lifespan_context", None)
            if lifespan_state and key in lifespan_state:
                return lifespan_state[key]
        except (AttributeError, TypeError):
            pass
    return _MISSING


def resolve_config(ctx: Optional[Any], key: str, loader: Callable[[], Any]) -> Any:
    """Resolve config from lifespan state or fallback to loader."""
    val = _from_lifespan(ctx, key)
    return val if val is not _MISSING else loader()


def resolve_cli_context(ctx: Optional[Any]) -> CliContext:
    """Resolve CliContext from lifespan state or build a fresh one."""
    val = _from_lifespan(ctx, "cli_context")
    return val if val is not _MISSING else resolve_collections_context()
