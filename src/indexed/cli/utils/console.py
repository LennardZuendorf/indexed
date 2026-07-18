"""Shared Rich console instance for the CLI.

This module provides a single Console instance used across all CLI commands
and the Loguru logging sink for consistent formatting and output. Routing
all output through one Console prevents conflicts between Rich
Live/Progress/Status displays and log messages.

Non-interactive environments (piped output, CI) degrade gracefully via
Console.is_terminal auto-detection.
"""

from typing import Optional

from rich.console import Console
from rich.text import Text

# Single shared console instance — ALL CLI output goes through this.
# Uses stdout (default) for compatibility with Typer's CliRunner in tests.
# Rich auto-detects non-interactive (piped) environments via Console.is_terminal.
console = Console()


def is_interactive() -> bool:
    """Check if the console is connected to an interactive terminal."""
    return console.is_terminal


def render_user_text(value: object, style: Optional[str] = None) -> Text:
    """Wrap user-/content-derived text so it is never markup-parsed.

    ``console`` above has Rich markup enabled (required for the app's own
    intentional style tags, e.g. ``[dim]...[/dim]``). Any string that
    originates outside this codebase — a search query, a collection name, a
    config value, a file path, a model name — must never be handed to a
    markup-parsed sink as a raw ``str``: bracket characters (``list[int]``)
    are parsed as style tags, silently dropping the bracketed portion or
    raising ``rich.errors.MarkupError``.

    Wrapping the value in a ``Text`` bypasses the markup parser entirely —
    Rich renders ``Text`` content literally — while still letting an
    optional ``style`` be applied (e.g. the app's dim/label style), exactly
    like a markup tag would, but without parsing ``value`` itself.

    Not suitable for `rich.progress.Progress` task descriptions: those are
    re-stringified and markup-reparsed by ``TextColumn``, so a wrapped
    ``Text`` degrades back into an unsafe plain string. Use
    ``rich.markup.escape`` for that sink instead.
    """
    return Text(str(value), style=style or "")


__all__ = ["console", "is_interactive", "render_user_text"]
