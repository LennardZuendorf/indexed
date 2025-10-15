"""Knowledge / Index Management CLI module.

This module provides the knowledge management subgroup and re-exports
individual commands for flat registration in the main app.
"""

import typer
from .commands import create, search, inspect, update, remove

# Create the knowledge subgroup (will be hidden in main app)
app = typer.Typer(help="Knowledge / Index Management commands")

# Register commands in the subgroup
app.add_typer(
    create.app, name="create", help="Create new collections (files, jira, confluence)"
)
app.command("search", help="Search indexed collections")(search.search)
app.command("inspect", help="Inspect indexed collections")(inspect.inspect_collections)
app.command("update", help="Update indexed collections")(update.update)
app.command("remove", help="Remove indexed collections")(remove.remove)

__all__ = ["app", "create", "search", "inspect", "update", "remove"]
