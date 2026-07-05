"""Indexed MCP Server using FastMCP.

Provides search and inspect capabilities for document collections via MCP tools and resources.
Uses FastMCP server lifespan and response caching middleware.
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Type, TypedDict

from fastmcp import FastMCP
from fastmcp.server.middleware.caching import ResponseCachingMiddleware

from core.v1.config_models import CoreV1SearchConfig, MCPConfig
from indexed_config import ConfigService

from indexed.bootstrap import register_app_config
from indexed.runtime import CliContext, resolve_collections_context

from .resources import register_resources
from .tools import register_tools


class LifespanState(TypedDict):
    """Type definition for lifespan state returned to tools/resources."""

    mcp_config: MCPConfig
    search_config: CoreV1SearchConfig
    cli_context: CliContext


def _get_config(model_cls: Type[Any]) -> Any:
    """Load configuration for the given model class, falling back to defaults."""
    try:
        provider = ConfigService.instance().bind()
        return provider.get(model_cls)
    except Exception:
        return model_cls()


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[LifespanState]:
    """Server lifespan context manager for configuration initialization."""
    config_service = ConfigService.instance()
    register_app_config(config_service)
    cli_context = resolve_collections_context()
    mcp_config = _get_config(MCPConfig)
    search_config = _get_config(CoreV1SearchConfig)
    yield {
        "mcp_config": mcp_config,
        "search_config": search_config,
        "cli_context": cli_context,
    }


mcp = FastMCP("Indexed MCP Server", lifespan=lifespan)
mcp.add_middleware(ResponseCachingMiddleware())

register_tools(mcp, lambda: _get_config(CoreV1SearchConfig))
register_resources(mcp, lambda: _get_config(MCPConfig))
