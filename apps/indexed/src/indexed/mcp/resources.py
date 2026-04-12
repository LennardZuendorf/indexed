"""MCP resource implementations for collection status."""

import logging
from typing import Any, Callable, Dict, List, Optional

from core.v1.engine.services import status as svc_status

from .config import resolve_config as _resolve_config

logger = logging.getLogger(__name__)


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


def register_resources(
    mcp: Any,
    get_mcp_config: Callable[[], Any],
    get_engine: Callable[[], str] = lambda: "v1",
) -> None:
    """Register collection resources on the FastMCP instance."""

    @mcp.resource(
        "resource://collections/{_all}",
        name="CollectionsList",
        description="Return list of available collection names.",
    )
    def collections_list(_all: str = "all") -> List[str] | Dict[str, str]:
        """Return list of available collection names."""
        try:
            engine = get_engine()
            if engine == "v2":
                from core.v2.services import status as v2_status

                statuses = v2_status()
            else:
                statuses = svc_status()
            return [status.name for status in statuses]
        except Exception as e:
            logger.debug("Failed to list collections: %s", e)
            return {"error": str(e)}

    @mcp.resource(
        "resource://collections/status/{_all}",
        name="CollectionsStatusList",
        description="Return detailed status information for all collections.",
    )
    def collections_status_list(
        _all: str = "all", ctx: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """Return detailed status information for all collections."""
        mcp_cfg = _resolve_config(ctx, "mcp_config", get_mcp_config)
        engine = _resolve_config(ctx, "engine", get_engine)

        try:
            if engine == "v2":
                from core.v2.services import status as v2_status

                statuses = v2_status()
            else:
                statuses = svc_status(include_index_size=mcp_cfg.include_index_size)
            return [_format_status(s) for s in statuses]
        except Exception as e:
            logger.debug("Failed to get collection statuses: %s", e)
            return [{"error": str(e)}]

    @mcp.resource(
        "resource://collections/{name}",
        name="CollectionStatus",
        description="Return detailed status information for a specific collection.",
    )
    def collection_status(name: str, ctx: Optional[Any] = None) -> Dict[str, Any]:
        """Get detailed status information for a named collection."""
        mcp_cfg = _resolve_config(ctx, "mcp_config", get_mcp_config)
        engine = _resolve_config(ctx, "engine", get_engine)

        try:
            if engine == "v2":
                from core.v2.services import status as v2_status

                statuses = v2_status([name])
            else:
                statuses = svc_status(
                    [name], include_index_size=mcp_cfg.include_index_size
                )
            if not statuses:
                return {"error": f"Collection '{name}' not found"}

            return _format_status(statuses[0])
        except Exception as e:
            logger.debug("Failed to get status for collection '%s': %s", name, e)
            return {"error": str(e)}
