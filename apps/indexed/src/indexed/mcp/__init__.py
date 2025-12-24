"""MCP Server package for indexed.

This package contains the FastMCP server implementation that exposes
indexed collections to AI agents via the Model Context Protocol.
"""

from .cli import app, run, dev, inspect, fastmcp, cli_main

__all__ = ["mcp", "main", "app", "run", "dev", "inspect", "fastmcp", "cli_main"]


# Lazy loading to avoid importing heavy dependencies (core.v1) during CLI startup
def __getattr__(name: str):
    if name == "mcp":
        from .server import mcp

        return mcp
    elif name == "main":
        from .server import main

        return main
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
