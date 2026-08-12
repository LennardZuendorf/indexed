"""Shared configuration resolution for MCP tools and resources."""

from typing import Any, Callable, Optional

from indexed.cli.composition import CliContext, resolve_collections_context

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
    """Resolve CliContext from lifespan state or build a fresh one.

    Fails CLOSED (workspace-profile/1, R1): the former
    ``default_global_context()`` swallowed every exception and handed back a
    hard-coded unfiltered context. With a collection allowlist in play that
    silently *widens* an agent's scope, so a malformed config now raises.
    """
    val = _from_lifespan(ctx, "cli_context")
    if val is not _MISSING:
        return val
    return resolve_collections_context()
