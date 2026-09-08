"""Exception hierarchy for the indexed CLI and MCP server."""

from __future__ import annotations

from indexed.config.errors import ConfigurationError, IndexedError, StorageError

EXIT_CODES: dict[type[IndexedError], int] = {
    ConfigurationError: 2,
    StorageError: 3,
}


class CLIError(IndexedError):
    """Base exception for CLI-related errors."""


class MCPError(IndexedError):
    """Base exception for MCP server errors."""


def format_cli_error(exc: IndexedError) -> str:
    return str(exc)


def exit_code_for(exc: IndexedError) -> int:
    for exc_type, code in EXIT_CODES.items():
        if isinstance(exc, exc_type):
            return code
    return 1


def mcp_error_envelope(exc: IndexedError) -> dict[str, str]:
    return {"error": str(exc), "type": type(exc).__name__}
