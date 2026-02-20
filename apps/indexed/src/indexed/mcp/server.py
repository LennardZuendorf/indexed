"""Indexed MCP Server using FastMCP.

Provides search and inspect capabilities for document collections via MCP tools and resources.
Uses FastMCP 2.13+ features including server lifespan and response caching middleware.
"""

# Suppress SWIG deprecation warnings from faiss (upstream issue, not fixed yet)
# Must be done before any faiss imports occur
import argparse
import warnings

warnings.filterwarnings("ignore", message="builtin type Swig.*")

from contextlib import asynccontextmanager  # noqa: E402
from typing import AsyncIterator, TypedDict  # noqa: E402

from fastmcp import FastMCP  # noqa: E402
from fastmcp.server.middleware.caching import ResponseCachingMiddleware  # noqa: E402

from core.v1.config_models import CoreV1SearchConfig, MCPConfig  # noqa: E402
from indexed_config import ConfigService  # noqa: E402

from .tools import register_tools  # noqa: E402
from .resources import register_resources  # noqa: E402


class LifespanState(TypedDict):
    """Type definition for lifespan state returned to tools/resources."""

    mcp_config: MCPConfig
    search_config: CoreV1SearchConfig


def _get_mcp_config() -> MCPConfig:
    """Load MCP configuration, falling back to defaults."""
    try:
        config_service = ConfigService.instance()
        config_service.register(MCPConfig, path="mcp")
        provider = config_service.bind()
        return provider.get(MCPConfig)
    except Exception:
        return MCPConfig()


def _get_search_config() -> CoreV1SearchConfig:
    """Load search configuration, falling back to defaults."""
    try:
        config_service = ConfigService.instance()
        config_service.register(CoreV1SearchConfig, path="core.v1.search")
        provider = config_service.bind()
        return provider.get(CoreV1SearchConfig)
    except Exception:
        return CoreV1SearchConfig()


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[LifespanState]:
    """Server lifespan context manager for configuration initialization."""
    mcp_config = _get_mcp_config()
    search_config = _get_search_config()
    yield {"mcp_config": mcp_config, "search_config": search_config}


# Create the FastMCP server instance with lifespan
mcp = FastMCP("Indexed MCP Server", lifespan=lifespan)

# Add response caching middleware for expensive search operations
mcp.add_middleware(ResponseCachingMiddleware())

# Register tools and resources
register_tools(mcp, _get_search_config)
register_resources(mcp, _get_mcp_config)


def main() -> None:
    """Main entry point for the MCP server."""
    mcp_cfg = _get_mcp_config()

    parser = argparse.ArgumentParser(description="MCP Server for indexed collections")
    parser.add_argument(
        "--host",
        default=mcp_cfg.host,
        help=f"Host to bind to (default: {mcp_cfg.host})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=mcp_cfg.port,
        help=f"Port to bind to (default: {mcp_cfg.port})",
    )
    parser.add_argument(
        "--log-level",
        default=mcp_cfg.log_level,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Log level (default: {mcp_cfg.log_level})",
    )

    args = parser.parse_args()

    mcp.run(host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
