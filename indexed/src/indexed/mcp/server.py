"""Indexed MCP Server using FastMCP.

Provides search and inspect capabilities for document collections via MCP tools and resources.
Uses FastMCP 2.13+ features including server lifespan and response caching middleware.
"""

# Suppress SWIG deprecation warnings from faiss (upstream issue, not fixed yet)
# Must be done before any faiss imports occur
import warnings

warnings.filterwarnings("ignore", message="builtin type Swig.*")

from contextlib import asynccontextmanager  # noqa: E402
from typing import Any, AsyncIterator, Dict, List, Optional, TypedDict  # noqa: E402

from fastmcp import FastMCP  # noqa: E402
from fastmcp.server.middleware.caching import ResponseCachingMiddleware  # noqa: E402

# Import ConfigService for configuration
from indexed_config import ConfigService  # noqa: E402
from core.v1.config_models import MCPConfig, CoreV1SearchConfig  # noqa: E402

# Import our service layer
from core.v1.engine.services import (  # noqa: E402
    search as svc_search,
    status as svc_status,
    SourceConfig,
)


class LifespanState(TypedDict):
    """Type definition for lifespan state returned to tools/resources."""

    mcp_config: MCPConfig
    search_config: CoreV1SearchConfig


def _get_mcp_config() -> MCPConfig:
    """Load MCP configuration from ConfigService.

    Returns:
        MCPConfig instance with values from config hierarchy
        (defaults -> global TOML -> workspace TOML -> env vars).
    """
    try:
        config_service = ConfigService.instance()
        config_service.register(MCPConfig, path="mcp")
        provider = config_service.bind()
        return provider.get(MCPConfig)
    except Exception:
        # Fallback to defaults if ConfigService unavailable
        return MCPConfig()


def _get_search_config() -> CoreV1SearchConfig:
    """Load search configuration from ConfigService.

    Returns:
        CoreV1SearchConfig instance with values from config hierarchy.
    """
    try:
        config_service = ConfigService.instance()
        config_service.register(CoreV1SearchConfig, path="core.v1.search")
        provider = config_service.bind()
        return provider.get(CoreV1SearchConfig)
    except Exception:
        # Fallback to defaults if ConfigService unavailable
        return CoreV1SearchConfig()


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[LifespanState]:
    """Server lifespan context manager for configuration initialization.

    This runs once when the server starts (not per-client session).
    Initializes configuration and yields it for use by tools/resources.

    Args:
        server: The FastMCP server instance

    Yields:
        LifespanState with mcp_config and search_config
    """
    # Initialize configuration at server startup
    mcp_config = _get_mcp_config()
    search_config = _get_search_config()

    yield {"mcp_config": mcp_config, "search_config": search_config}


# Create the FastMCP server instance with lifespan
mcp = FastMCP("Indexed MCP Server", lifespan=lifespan)

# Add response caching middleware for expensive search operations
# This caches tool and resource call results with TTL-based expiration
mcp.add_middleware(ResponseCachingMiddleware())


# Legacy config accessors for backward compatibility and non-lifespan contexts
_mcp_config: Optional[MCPConfig] = None
_search_config: Optional[CoreV1SearchConfig] = None


def get_mcp_config() -> MCPConfig:
    """Get cached MCP configuration (fallback for non-lifespan contexts)."""
    global _mcp_config
    if _mcp_config is None:
        _mcp_config = _get_mcp_config()
    return _mcp_config


def get_search_config() -> CoreV1SearchConfig:
    """Get cached search configuration (fallback for non-lifespan contexts)."""
    global _search_config
    if _search_config is None:
        _search_config = _get_search_config()
    return _search_config


@mcp.tool
def search(query: str) -> Dict[str, Any]:
    """
    Search across all available document collections using semantic similarity.

    Args:
        query: The search query text

    Returns:
        Dictionary with collection names as keys and search results as values
    """
    search_cfg = get_search_config()

    try:
        # Use auto-discovery mode (configs=None) to search all collections
        results = svc_search(
            query,
            configs=None,
            max_docs=search_cfg.max_docs,
            max_chunks=search_cfg.max_chunks,
            score_threshold=search_cfg.score_threshold,
            include_full_text=search_cfg.include_full_text,
            include_all_chunks=search_cfg.include_all_chunks,
            include_matched_chunks=search_cfg.include_matched_chunks,
        )
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def search_collection(collection: str, query: str) -> Dict[str, Any]:
    """
    Search within a specific document collection using semantic similarity.

    Uses the same configuration as the search tool from ConfigService.

    Args:
        collection: Name of the collection to search
        query: The search query text

    Returns:
        Dictionary with search results for the specified collection
    """
    search_cfg = get_search_config()

    try:
        # Get default indexer for the collection from inspect service
        try:
            statuses = svc_status([collection])
            if not statuses or not statuses[0].indexers:
                return {
                    "error": f"Collection '{collection}' not found or has no indexers"
                }

            default_indexer = statuses[0].indexers[0]
        except Exception:
            # Fallback to default indexer
            from core.v1.constants import DEFAULT_INDEXER

            default_indexer = DEFAULT_INDEXER

        # Create SourceConfig for the specific collection
        source_config = SourceConfig(
            name=collection,
            type="localFiles",  # Type doesn't matter for search
            base_url_or_path="",  # Not used for search
            indexer=default_indexer,
        )

        results = svc_search(
            query,
            configs=[source_config],
            max_docs=search_cfg.max_docs,
            max_chunks=search_cfg.max_chunks,
            score_threshold=search_cfg.score_threshold,
            include_full_text=search_cfg.include_full_text,
            include_all_chunks=search_cfg.include_all_chunks,
            include_matched_chunks=search_cfg.include_matched_chunks,
        )
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.resource(
    "resource://collections",
    name="CollectionsList",
    description="Return list of available collection names.",
)
def collections_list() -> List[str]:
    """Return list of available collection names."""
    try:
        statuses = svc_status()
        return [status.name for status in statuses]
    except Exception as e:
        return [f"error: {str(e)}"]


@mcp.resource(
    "resource://collections/status",
    name="CollectionsStatusList",
    description="Return detailed status information for all collections.",
)
def collections_status_list() -> List[Dict[str, Any]]:
    """
    Return detailed status information for all collections.

    Configuration via ConfigService (mcp.include_index_size).
    """
    mcp_cfg = get_mcp_config()
    
    try:
        statuses = svc_status(include_index_size=mcp_cfg.include_index_size)
        # Convert CollectionStatus objects to dictionaries
        return [
            {
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
            for s in statuses
        ]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.resource(
    "resource://collections/{name}",
    name="CollectionStatus",
    description="Return detailed status information for a specific collection.",
)
def collection_status(name: str) -> Dict[str, Any]:
    """
    Return detailed status information for a specific collection.

    Uses the same configuration as collections_status_list.
    """
    mcp_cfg = get_mcp_config()
    
    try:
        statuses = svc_status([name], include_index_size=mcp_cfg.include_index_size)
        if not statuses:
            return {"error": f"Collection '{name}' not found"}

        s = statuses[0]
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
    except Exception as e:
        return {"error": str(e)}


def main():
    """Main entry point for the MCP server."""
    import argparse

    # Get MCP config for defaults
    mcp_cfg = get_mcp_config()
    
    parser = argparse.ArgumentParser(description="MCP Server for indexed collections")
    parser.add_argument(
        "--host", default=mcp_cfg.host, help=f"Host to bind to (default: {mcp_cfg.host})"
    )
    parser.add_argument(
        "--port", type=int, default=mcp_cfg.port, help=f"Port to bind to (default: {mcp_cfg.port})"
    )
    parser.add_argument(
        "--log-level",
        default=mcp_cfg.log_level,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Log level (default: {mcp_cfg.log_level})",
    )

    args = parser.parse_args()

    # Run the FastMCP server with parsed arguments
    mcp.run(host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
