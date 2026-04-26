"""Exception hierarchy for the indexed CLI and MCP server."""

from __future__ import annotations

from indexed_config.errors import IndexedError


class CLIError(IndexedError):
    """Base exception for CLI-related errors."""


class MCPError(IndexedError):
    """Base exception for MCP server errors."""
