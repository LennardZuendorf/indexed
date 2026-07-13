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
"""

from typing import Any, Callable, Dict, Optional

from fastmcp import Context
from loguru import logger

from indexed.core.v1.engine import status as svc_status
from indexed.config.errors import IndexedError

from indexed.cli.errors import MCPError, mcp_error_envelope
from .config import resolve_cli_context, resolve_config as _resolve_config


def _format_status(s: Any) -> Dict[str, Any]:
    """Format a status object into a serializable dict."""
    return {
        "name": s.name,
        "number_of_documents": s.number_of_documents,
        "number_of_chunks": s.number_of_chunks,
        "updated_time": s.updated_time,
        "last_modified_document_time": s.last_modified_document_time,
        "indexers": s.indexers,
        "index_size": s.index_size,
        "source_type": s.source_type,
        "relative_path": s.relative_path,
        "disk_size_bytes": s.disk_size_bytes,
    }


def register_resources(mcp: Any, get_mcp_config: Callable[[], Any]) -> None:
    """Register collection resources on the FastMCP instance."""

    @mcp.resource(
        "resource://collections",
        name="CollectionsList",
        description="Return list of available collection names.",
    )
    def collections_list(ctx: Optional[Context] = None) -> Dict[str, Any]:
        cli_ctx = resolve_cli_context(ctx)
        collections_path = str(cli_ctx.collections_path)
        try:
            statuses = svc_status(collections_path=collections_path)
            return {"collections": [s.name for s in statuses]}
        except IndexedError as e:
            return mcp_error_envelope(e)

    @mcp.resource(
        "resource://collections/status",
        name="CollectionsStatusList",
        description="Return detailed status information for all collections.",
    )
    def collections_status_list(ctx: Optional[Context] = None) -> Dict[str, Any]:
        mcp_cfg = _resolve_config(ctx, "mcp_config", get_mcp_config)
        cli_ctx = resolve_cli_context(ctx)
        collections_path = str(cli_ctx.collections_path)
        try:
            statuses = svc_status(
                include_index_size=mcp_cfg.include_index_size,
                collections_path=collections_path,
            )
            return {"collections": [_format_status(s) for s in statuses]}
        except IndexedError as e:
            return mcp_error_envelope(e)

    @mcp.resource(
        "resource://collection/{name}",
        name="CollectionStatus",
        description="Return detailed status information for a specific collection.",
    )
    def collection_status(name: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
        mcp_cfg = _resolve_config(ctx, "mcp_config", get_mcp_config)
        cli_ctx = resolve_cli_context(ctx)
        collections_path = str(cli_ctx.collections_path)
        try:
            statuses = svc_status(
                [name],
                include_index_size=mcp_cfg.include_index_size,
                collections_path=collections_path,
            )
            if not statuses:
                return {"error": f"Collection '{name}' not found"}
            return _format_status(statuses[0])
        except IndexedError as e:
            return mcp_error_envelope(e)
        except Exception as e:  # noqa: BLE001 - MCP boundary must never leak a raw error
            logger.exception(
                "Unexpected error resolving status for collection '{}'", name
            )
            return mcp_error_envelope(MCPError(f"Internal error: {e}"))
