"""Knowledge / Index Management CLI module.

This module provides the knowledge management subgroup and re-exports
individual commands for flat registration in the main app.
"""

import webbrowser
import typer

from .commands import create, search, inspect, update, remove
from ..utils.console import console
from ..utils.components.theme import get_success_style, get_secondary_style

app = typer.Typer(help="Knowledge / Index Management commands")

app.add_typer(create.app, name="create", help="Create new collections")
app.command("search", help="Search collections")(search.search)
app.command("inspect", help="Inspect collections")(inspect.inspect_collections)
app.command("update", help="Update collections")(update.update)
app.command("remove", help="Remove collections")(remove.remove)


@app.command("docs", rich_help_panel="Resources")
def docs() -> None:
    """
    Open the index documentation URL in the user's default web browser.

    Prints a success message and the documentation URL when the browser is opened. If opening the browser fails, prints an error and the URL and exits the process with code 1.
    """
    url = "https://indexed.ignitr.dev/docs/indexing"
    try:
        webbrowser.open(url)
        console.print()
        console.print(
            f"[{get_success_style()}]✓[/{get_success_style()}] Opening indexing documentation in browser..."
        )
        console.print(f"[{get_secondary_style()}]{url}[/{get_secondary_style()}]")
        console.print()
    except Exception as e:
        console.print()
        console.print(f"Failed to open browser: {e}")
        console.print(f"Visit manually: {url}")
        console.print()
        raise typer.Exit(1)


__all__ = ["app", "create", "search", "inspect", "update", "remove"]
