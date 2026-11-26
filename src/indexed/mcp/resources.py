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

import asyncio
from typing import Any, Callable, Dict, List, Optional

from fastmcp import Context
from loguru import logger

from indexed.core.engine import status as svc_status
from indexed.config.errors import IndexedError

from indexed.cli.errors import MCPError, mcp_error_envelope
from indexed.cli.search_sources import declare_sources, scope_of
from .collection_errors import unresolvable_collection_error
from .config import resolve_config as _resolve_config
from .scope import RequestScope, require_in_scope, resolve_request_scope


def _format_status(s: Any) -> Dict[str, Any]:
    """Format a status object into a serializable dict."""
    # Opt-in freshness-vs-working-tree verdict (#146 slice 1); absent for a
    # plain status poll so it stays git-free. A non-dict (e.g. a mock from a
    # caller's test) is treated as absent rather than serialized.
    verdict = getattr(s, "freshness", None)
    out = {
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
    if isinstance(verdict, dict):
        out["freshness"] = verdict
    return out


def _boundary_envelope(exc: Exception, context: str) -> Dict[str, Any]:
    """Envelope any failure raised while serving a resource (issue #125).

    ``docs/spec/tech/app/app-mcp-freshness-errors.md`` states this boundary
    envelopes **every** exception, so an agent sees a failure, never a protocol
    error it cannot read: an ``IndexedError`` keeps its own class name in the
    envelope, anything else — an unreadable collections root raising
    ``PermissionError`` out of the status scan, an ``OSError`` — is logged in
    full and wrapped as ``MCPError``, the same contract ``tools.py`` has always
    honoured. The two list resources used to catch only ``IndexedError``, so
    those escaped and cost every client the whole listing.
    """
    if isinstance(exc, IndexedError):
        return mcp_error_envelope(exc)
    logger.exception("Unexpected error {}", context)
    return mcp_error_envelope(MCPError(f"Internal error: {exc}"))


async def _scoped_statuses(
    scope: RequestScope, **status_kwargs: Any
) -> "tuple[Optional[List[Any]], Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]":
    """The request's selected collections' statuses, in definition order.

    Returns ``(statuses, declarations, None)`` or ``(None, None, envelope)``.
    Status is the surface an agent uses to check what it can see, so it applies
    exactly the scope search applies — and names a selected collection the store
    can no longer serve in ``sources`` instead of dropping it silently (#340).

    The scan is asked for the request's own names (not the whole store) and runs
    in a worker thread: this server answers many clients from one event loop.
    """
    collections_path = str(scope.collections_path)
    try:
        statuses = await asyncio.to_thread(
            svc_status,
            list(scope.selection.scope),
            collections_path=collections_path,
            **status_kwargs,
        )
    except Exception as e:  # noqa: BLE001 - MCP boundary must never leak a raw error
        return None, None, _boundary_envelope(e, "while listing collection statuses")

    names, unresolved = scope_of(scope.selection, statuses)
    declarations = declare_sources(
        names=names, statuses=statuses, unresolved=unresolved
    )
    by_name = {status.name: status for status in statuses}
    selected = [
        by_name[str(declaration["collection"])]
        for declaration in declarations
        if "status" not in declaration
    ]
    return selected, declarations, None


def register_resources(mcp: Any, get_mcp_config: Callable[[], Any]) -> None:
    """Register collection resources on the FastMCP instance."""

    @mcp.resource(
        "resource://collections",
        name="CollectionsList",
        description=("Return the collection names this client's repository selects."),
    )
    async def collections_list(ctx: Optional[Context] = None) -> Dict[str, Any]:
        try:
            scope = await resolve_request_scope(ctx)
        except IndexedError as e:
            return mcp_error_envelope(e)
        statuses, declarations, error = await _scoped_statuses(scope)
        if error is not None:
            return error
        return {
            "collections": [s.name for s in statuses or []],
            "sources": declarations,
        }

    @mcp.resource(
        "resource://collections/status",
        name="CollectionsStatusList",
        description=(
            "Return detailed status for the collections this client's repository "
            "selects."
        ),
    )
    async def collections_status_list(ctx: Optional[Context] = None) -> Dict[str, Any]:
        mcp_cfg = _resolve_config(ctx, "mcp_config", get_mcp_config)
        try:
            scope = await resolve_request_scope(ctx)
        except IndexedError as e:
            return mcp_error_envelope(e)
        statuses, declarations, error = await _scoped_statuses(
            scope, include_index_size=mcp_cfg.include_index_size, include_freshness=True
        )
        if error is not None:
            return error
        return {
            "collections": [_format_status(s) for s in statuses or []],
            "sources": declarations,
        }

    @mcp.resource(
        "resource://collection/{name}",
        name="CollectionStatus",
        description="Return detailed status information for a specific collection.",
    )
    async def collection_status(
        name: str, ctx: Optional[Context] = None
    ) -> Dict[str, Any]:
        mcp_cfg = _resolve_config(ctx, "mcp_config", get_mcp_config)
        try:
            scope = await resolve_request_scope(ctx)
            require_in_scope(scope, name)
        except IndexedError as e:
            return mcp_error_envelope(e)
        collections_path = str(scope.collections_path)
        try:
            statuses = await asyncio.to_thread(
                svc_status,
                [name],
                include_index_size=mcp_cfg.include_index_size,
                collections_path=collections_path,
                include_freshness=True,
            )
            if not statuses:
                return unresolvable_collection_error(
                    name, collections_path, f"Collection '{name}' not found"
                )
            return _format_status(statuses[0])
        except Exception as e:  # noqa: BLE001 - MCP boundary must never leak a raw error
            return _boundary_envelope(e, f"resolving status for collection '{name}'")
