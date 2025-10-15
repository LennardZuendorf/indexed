"""Shared Rich console instance for the CLI.

This module provides a single Console instance to be used across all CLI commands
for consistent formatting and output.
"""

from rich.console import Console

# Shared console instance
console = Console()

__all__ = ["console"]
