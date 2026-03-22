"""Shared Rich console instance and output helpers for the CLI.

This module provides:
- A single Console(stderr=True) instance shared across the entire CLI
- Consistent output helpers: success(), error(), warning(), info(), step()
- All CLI output routes through this single console to avoid Rich/Loguru conflicts

Non-interactive environments (piped output, CI) degrade gracefully via
Console.is_terminal auto-detection.
"""

from rich.console import Console

# Single shared console instance — ALL CLI output goes through this.
# Uses stdout (default) for compatibility with Typer's CliRunner in tests.
# Rich auto-detects non-interactive (piped) environments via Console.is_terminal.
console = Console()

# Icons (simple unicode, not emoji)
_ICON_SUCCESS = "\u2713"  # ✓
_ICON_ERROR = "\u2717"  # ✗
_ICON_WARNING = "\u26a0"  # ⚠
_ICON_INFO = "\u2139"  # ℹ


def success(msg: str) -> None:
    """Print a success message with green ✓ prefix."""
    console.print(f"[green]{_ICON_SUCCESS}[/green] {msg}")


def error(msg: str) -> None:
    """Print an error message with red ✗ prefix."""
    console.print(f"[red]{_ICON_ERROR}[/red] {msg}")


def warning(msg: str) -> None:
    """Print a warning message with yellow ⚠ prefix."""
    console.print(f"[yellow]{_ICON_WARNING}[/yellow] {msg}")


def info(msg: str) -> None:
    """Print an informational message in dim text.

    Only shown when verbose mode is enabled — callers should check
    is_verbose_mode() before calling, or use this in verbose-only paths.
    """
    console.print(f"[dim]{msg}[/dim]")


def step(n: int, total: int, msg: str) -> None:
    """Print a numbered step in a sequence.

    Example: step(1, 4, "Loading model") → "[1/4] Loading model"
    """
    console.print(f"[bold]\\[{n}/{total}][/bold] {msg}")


def plain_print(msg: str) -> None:
    """Print plain text, bypassing Rich markup.

    Useful for non-interactive/piped output where Rich formatting
    should not be applied.
    """
    console.print(msg, highlight=False, markup=False)


def is_interactive() -> bool:
    """Check if the console is connected to an interactive terminal."""
    return console.is_terminal


__all__ = [
    "console",
    "success",
    "error",
    "warning",
    "info",
    "step",
    "plain_print",
    "is_interactive",
]
