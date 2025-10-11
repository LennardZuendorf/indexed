"""MCP Server package for indexed.

This package contains the FastMCP server implementation that exposes
indexed collections to AI agents via the Model Context Protocol.
"""

from .server import mcp, main
from .cli import app, run, dev, inspect, fastmcp, cli_main

__all__ = ["mcp", "main", "app", "run", "dev", "inspect", "fastmcp", "cli_main"]
