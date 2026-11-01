"""Rich consoles for the CLI: stdout for user output, stderr for log records.

``console`` carries what a human reads — results, cards, progress displays —
and is stdout-backed. ``log_console`` is the Loguru sink target and is
stderr-backed, because stdout is the machine stream: under ``--json`` /
``--simple-output`` it holds the payload and nothing else, so a log record
must never land there. Both are Rich consoles, so formatting and theme styles
stay in one place; Rich resolves ``sys.stdout``/``sys.stderr`` lazily per
write, so Typer's ``CliRunner`` capture keeps working for both.

Non-interactive environments (piped output, CI) degrade gracefully via
Console.is_terminal auto-detection.
"""

from typing import Optional

from rich.console import Console
from rich.text import Text

# Single shared console instance — ALL human-facing CLI output goes through this.
# Uses stdout (default) for compatibility with Typer's CliRunner in tests.
# Rich auto-detects non-interactive (piped) environments via Console.is_terminal.
console = Console()

# The Loguru sink (``bootstrap_logging(rich_console=...)``) writes here, never
# to ``console``: stdout belongs to the command's machine output.
log_console = Console(stderr=True)


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


__all__ = ["console", "is_interactive", "log_console", "render_user_text"]
