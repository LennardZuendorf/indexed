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
