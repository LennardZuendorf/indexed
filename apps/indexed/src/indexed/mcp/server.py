"""Indexed MCP Server using FastMCP.

Provides search and inspect capabilities for document collections via MCP tools and resources.
Uses FastMCP server lifespan and response caching middleware.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator, TypedDict

from fastmcp import FastMCP
from fastmcp.server.middleware.caching import ResponseCachingMiddleware

from core.v1.config_models import CoreV1SearchConfig, MCPConfig
from indexed_config import ConfigService

from .resources import register_resources
from .tools import register_tools


class LifespanState(TypedDict):
    """Type definition for lifespan state returned to tools/resources."""

    mcp_config: MCPConfig
    search_config: CoreV1SearchConfig
    engine: str


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


def _get_engine() -> str:
    """Load engine selection from config, defaulting to v1."""
    try:
        from ..services.engine_router import GeneralConfig

        config_service = ConfigService.instance()
        config_service.register(GeneralConfig, path="general")
        provider = config_service.bind()
        return str(provider.get(GeneralConfig).engine)
    except Exception:
        return "v1"


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[LifespanState]:
    """Server lifespan context manager for configuration initialization."""
    mcp_config = _get_mcp_config()
    search_config = _get_search_config()
    engine = _get_engine()
    yield {"mcp_config": mcp_config, "search_config": search_config, "engine": engine}


mcp = FastMCP("Indexed MCP Server", lifespan=lifespan)
mcp.add_middleware(ResponseCachingMiddleware())

# Register tools and resources with engine routing
register_tools(mcp, _get_search_config, _get_engine)
register_resources(mcp, _get_mcp_config, _get_engine)
