"""Indexed MCP Server using FastMCP.

Provides search and inspect capabilities for document collections via MCP tools and resources.
Uses FastMCP server lifespan for configuration initialization.

No response-caching middleware is registered: the searcher cache in
``SearchService`` already provides the latency win, and a TTL cache here would
serve stale results (including cached error envelopes) for up to an hour after
a re-index (foundation/6 E9).
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Type, TypedDict

from fastmcp import FastMCP

from indexed.core.v1.config_models import CoreV1SearchConfig, MCPConfig
from indexed.config import get_config

from indexed.cli.composition import register_app_config
from indexed.cli.composition import CliContext

from .config import resolve_cli_context
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
        provider = get_config().bind()
        return provider.get(model_cls)
    except Exception:
        return model_cls()


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[LifespanState]:
    """Server lifespan context manager for configuration initialization."""
    config_service = get_config()
    register_app_config(config_service)
    # No lifespan context exists yet during startup, so this call always
    # falls through resolve_cli_context's fresh-resolution path (R2),
    # degrading to a default global-mode context rather than letting a
    # malformed/unreadable config.toml crash server startup.
    cli_context = resolve_cli_context(None)
    mcp_config = _get_config(MCPConfig)
    search_config = _get_config(CoreV1SearchConfig)
    yield {
        "mcp_config": mcp_config,
        "search_config": search_config,
        "cli_context": cli_context,
    }


mcp = FastMCP("Indexed MCP Server", lifespan=lifespan)

register_tools(mcp, lambda: _get_config(CoreV1SearchConfig))
register_resources(mcp, lambda: _get_config(MCPConfig))
