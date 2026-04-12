"""Engine selection router — dispatches to v1 or v2 service modules.

Resolution order (highest priority first):
1. Per-command ``--engine`` flag (passed as ``command_engine`` arg)
2. Root callback ``--engine`` flag stored in ``ctx.obj["engine"]``
3. ``[general] engine`` key in config.toml
4. Default: ``"v1"``
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class GeneralConfig(BaseModel):
    """Top-level [general] section of config.toml."""

    engine: Literal["v1", "v2"] = Field(
        default="v1",
        description="Core engine version: v1 (default) or v2 (LlamaIndex-powered)",
    )


def get_effective_engine(command_engine: Optional[str] = None) -> str:
    """Resolve the active engine for the current call.

    Args:
        command_engine: Per-command ``--engine`` flag value (highest priority).

    Returns:
        ``"v1"`` or ``"v2"``.
    """
    if command_engine and isinstance(command_engine, str):
        return command_engine.lower()

    # Root callback flag stored on Typer context
    try:
        import click

        ctx = click.get_current_context()
        root_engine: Any = (ctx.obj or {}).get("engine")
        if root_engine:
            return str(root_engine)
    except (RuntimeError, AttributeError):
        pass  # No active Typer context (e.g., during unit tests)

    # Fall back to [general] engine in config
    try:
        from indexed_config import ConfigService

        config = ConfigService.instance()
        provider = config.bind()
        general = provider.get(GeneralConfig)
        return str(general.engine)
    except Exception:
        pass

    return "v1"


def get_collection_service(engine: str) -> Any:
    """Return the collection service module for the given engine.

    The returned module exposes ``create``, ``update``, and ``clear``.
    """
    if engine == "v2":
        from core.v2.services import collection_service

        return collection_service
    from core.v1.engine.services import collection_service

    return collection_service


def get_search_service(engine: str) -> Any:
    """Return the search service module for the given engine.

    The returned module exposes ``search`` and ``SearchService``.
    """
    if engine == "v2":
        from core.v2.services import search_service

        return search_service
    from core.v1.engine.services import search_service

    return search_service


def get_inspect_service(engine: str) -> Any:
    """Return the inspect service module for the given engine.

    The returned module exposes ``status`` and ``inspect``.
    """
    if engine == "v2":
        from core.v2.services import inspect_service

        return inspect_service
    from core.v1.engine.services import inspect_service

    return inspect_service
