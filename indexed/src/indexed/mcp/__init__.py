"""MCP Server package for indexed.

This package contains the FastMCP server implementation that exposes
indexed collections to AI agents via the Model Context Protocol.
"""

from .server import mcp, main

__all__ = ["mcp", "main"]
