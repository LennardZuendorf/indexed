"""Shared configuration resolution for MCP tools and resources."""

from typing import Any, Callable, Optional


from indexed.runtime import CliContext, resolve_collections_context


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


def resolve_cli_context(ctx: Optional[Any]) -> CliContext:
    """Resolve CliContext from lifespan state or build a fresh one."""
    if ctx is not None:
        try:
            lifespan_state = getattr(ctx, "lifespan_context", None)
            if lifespan_state and "cli_context" in lifespan_state:
                return lifespan_state["cli_context"]
        except (AttributeError, TypeError):
            pass
    return resolve_collections_context()
