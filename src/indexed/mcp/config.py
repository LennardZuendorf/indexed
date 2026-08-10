"""Shared configuration resolution for MCP tools and resources."""

from collections.abc import Callable
from typing import Any

from loguru import logger

from indexed.cli.composition import CliContext, resolve_collections_context
from indexed.config import get_config

_MISSING = object()


def _from_lifespan(ctx: Any | None, key: str) -> Any:
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


def resolve_config(ctx: Any | None, key: str, loader: Callable[[], Any]) -> Any:
    """Resolve config from lifespan state or fallback to loader."""
    val = _from_lifespan(ctx, key)
    return val if val is not _MISSING else loader()


def default_global_context() -> CliContext:
    """Build a minimal global-mode CliContext without reading config.toml.

    Used as the degraded fallback (R2) when resolving the real CLI context
    fails — e.g. a malformed global ``config.toml`` raising
    ``TOMLDecodeError`` out of ``get_preference``/``read_for_mode``. Those
    stay fail-loud (the CLI's own error path depends on it); this builds
    paths directly from an explicit "global" preference, which short-circuits
    the storage-mode cascade before it ever touches the on-disk config.
    """
    config_service = get_config()
    resolver = config_service.resolver
    return CliContext(
        mode="global",
        collections_path=resolver.get_collections_path("global"),
        caches_path=resolver.get_caches_path("global"),
        config_service=config_service,
    )


def resolve_cli_context(ctx: Any | None) -> CliContext:
    """Resolve CliContext from lifespan state or build a fresh one.

    Falls back to a default global-mode context (R2) when resolution fails
    (e.g. malformed/unreadable config.toml) rather than letting the error
    escape and crash the request.
    """
    val = _from_lifespan(ctx, "cli_context")
    if val is not _MISSING:
        return val
    try:
        return resolve_collections_context()
    except Exception as exc:
        logger.warning(f"Failed to resolve CLI context, using default: {exc}")
        return default_global_context()
