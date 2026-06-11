"""Indexed MCP Server using FastMCP.

Provides search and inspect capabilities for document collections via MCP tools and resources.
Uses FastMCP server lifespan and response caching middleware.

Configuration and engine selection are resolved ONCE in :func:`lifespan` and
stored in lifespan state. Tools and resources read them back through the single
helper in :mod:`indexed.mcp.config` — there is no module-level config global and
no per-call fallback loading.
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
    """Resolve the active engine via the engine router, defaulting to v2.

    Delegates to :func:`engine_router.get_effective_engine` so the resolution
    order (CLI flag → root callback → config) lives in one place. Falls back to
    ``"v2"`` only when the router cannot be reached.
    """
    try:
        from ..services.engine_router import get_effective_engine

        return get_effective_engine()
    except Exception:
        return "v2"


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[LifespanState]:
    """Server lifespan context manager for configuration initialization."""
    mcp_config = _get_mcp_config()
    search_config = _get_search_config()
    engine = _get_engine()
    yield {"mcp_config": mcp_config, "search_config": search_config, "engine": engine}


mcp = FastMCP("Indexed MCP Server", lifespan=lifespan)
mcp.add_middleware(ResponseCachingMiddleware())

# Register tools and resources. Engine and config come from lifespan state at
# request time; the registration default engine is "v2".
register_tools(mcp)
register_resources(mcp)
