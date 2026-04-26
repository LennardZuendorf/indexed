"""MCP Server package for indexed.

This package contains the FastMCP server implementation that exposes
indexed collections to AI agents via the Model Context Protocol.
"""

from .cli import app, cli_main, dev, inspect, run

__all__ = ["mcp", "app", "run", "dev", "inspect", "cli_main"]


# Lazy loading to avoid importing heavy dependencies (core.v1) during CLI startup
def __getattr__(name: str) -> object:
    if name == "mcp":
        from .server import mcp

        return mcp
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
