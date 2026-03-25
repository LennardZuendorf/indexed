"""Shared Rich console instance for the CLI.

This module provides a single Console instance used across all CLI commands
and the Loguru logging sink for consistent formatting and output. Routing
all output through one Console prevents conflicts between Rich
Live/Progress/Status displays and log messages.

Non-interactive environments (piped output, CI) degrade gracefully via
Console.is_terminal auto-detection.
"""

from rich.console import Console

# Single shared console instance — ALL CLI output goes through this.
# Uses stdout (default) for compatibility with Typer's CliRunner in tests.
# Rich auto-detects non-interactive (piped) environments via Console.is_terminal.
console = Console()


def is_interactive() -> bool:
    """Check if the console is connected to an interactive terminal."""
    return console.is_terminal


__all__ = ["console", "is_interactive"]
