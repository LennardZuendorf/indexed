"""MCP resource implementations for collection status.

URI design (FastMCP v3 dispatches by path shape, so `{a}` and `{b}` collide
when the surrounding paths are identical — disjoint structural patterns
keep dispatch unambiguous):

- `resource://collections`             → list collection names (static)
- `resource://collections/status`      → status for all collections (static)
- `resource://collection/{name}`       → status for a single collection (template, singular)

FastMCP v3 also rejects bare list/dict returns — a list is iterated as
`ResourceContent` slots and fails on each element. All resources therefore
return a dict envelope so v3 serializes them as a single JSON content block.

Engine selection is read from the server lifespan state and resolved through
the engine router; concrete v1/v2 service modules come from
``get_inspect_service`` (which lazily imports the heavy stacks).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastmcp import Context

from indexed_config.errors import IndexedError

from ..services.engine_router import get_inspect_service
from .config import (
    get_lifespan_value,
    resolve_engine_for_collection,
)

logger = logging.getLogger(__name__)

DEFAULT_ENGINE = "v2"


def _format_status(s: Any) -> Dict[str, Any]:
    """Format a status object into a serializable dict."""
    return {
        "name": s.name,
        "number_of_documents": s.number_of_documents,
        "number_of_chunks": s.number_of_chunks,
        "updated_time": s.updated_time,
        "last_modified_document_time": getattr(s, "last_modified_document_time", None),
        "indexers": getattr(s, "indexers", []),
        "index_size": getattr(s, "index_size", None),
        "source_type": getattr(s, "source_type", None),
        "relative_path": getattr(s, "relative_path", None),
        "disk_size_bytes": getattr(s, "disk_size_bytes", None),
    }


def _status_for_engine(
    engine: str,
    names: Optional[list[str]],
    *,
    include_index_size: bool,
) -> list[Any]:
    """Fetch collection statuses through the engine router.

    v1 and v2 ``status`` signatures diverge (v1: ``include_index_size`` +
    ``collections_path``; v2: ``collections_dir`` for local-storage support),
    so the call is branched per engine while the module comes from the router.
    """
    inspect_service = get_inspect_service(engine)

    if engine == "v2":
        from ..utils.storage_info import resolve_preferred_collections_path

        collections_dir = resolve_preferred_collections_path()
        return list(inspect_service.status(names, collections_dir=collections_dir))

    if names is None:
        return list(inspect_service.status(include_index_size=include_index_size))
    return list(inspect_service.status(names, include_index_size=include_index_size))


def register_resources(mcp: Any) -> None:
    """Register collection resources on the FastMCP instance."""

    @mcp.resource(
        "resource://collections",
        name="CollectionsList",
        description="Return list of available collection names.",
    )
    def collections_list(ctx: Optional[Context] = None) -> Dict[str, Any]:
        engine = str(get_lifespan_value(ctx, "engine", DEFAULT_ENGINE))
        try:
            statuses = _status_for_engine(engine, None, include_index_size=False)
            return {"collections": [s.name for s in statuses]}
        except IndexedError as e:
            logger.debug("Failed to list collections: %s", e)
            return {"error": str(e)}

    @mcp.resource(
        "resource://collections/status",
        name="CollectionsStatusList",
        description="Return detailed status information for all collections.",
    )
    def collections_status_list(ctx: Optional[Context] = None) -> Dict[str, Any]:
        mcp_cfg = _mcp_config_from_ctx(ctx)
        engine = str(get_lifespan_value(ctx, "engine", DEFAULT_ENGINE))

        try:
            statuses = _status_for_engine(
                engine, None, include_index_size=mcp_cfg.include_index_size
            )
            return {"collections": [_format_status(s) for s in statuses]}
        except IndexedError as e:
            logger.debug("Failed to get collection statuses: %s", e)
            return {"error": str(e)}

    @mcp.resource(
        "resource://collection/{name}",
        name="CollectionStatus",
        description="Return detailed status information for a specific collection.",
    )
    def collection_status(name: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
        mcp_cfg = _mcp_config_from_ctx(ctx)
        engine = resolve_engine_for_collection(name, ctx, DEFAULT_ENGINE)

        try:
            statuses = _status_for_engine(
                engine, [name], include_index_size=mcp_cfg.include_index_size
            )
            if not statuses:
                return {"error": f"Collection '{name}' not found"}
            return _format_status(statuses[0])
        except IndexedError as e:
            logger.debug("Failed to get status for collection '%s': %s", name, e)
            return {"error": str(e)}


def _mcp_config_from_ctx(ctx: Optional[Context]) -> Any:
    """Read the MCP config from lifespan state, defaulting to config defaults."""
    from core.v1.config_models import MCPConfig

    return get_lifespan_value(ctx, "mcp_config", MCPConfig())
