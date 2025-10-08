"""Inspect command - Show indexed collections or detailed info about a specific collection.

This command uses the core inspect() service to fetch collection data and the
inspect_formatter to display it beautifully with Rich. It's completely decoupled
from the underlying data storage and connection mechanisms.
"""

import typer

from cli.utils.console import console
from cli.formatters.inspect_formatter import (
    format_collection_list,
    format_collection_detail,
    format_collection_json,
    format_collections_json,
)
from core.v1.engine.services import inspect


def inspect_collections(
    name: str = typer.Argument(None, help="Collection name to inspect in detail"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information for all collections"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show all indexed collections or inspect a specific collection.
    
    Examples:
        indexed inspect                    # List all collections
        indexed inspect my-collection      # Detailed info about specific collection
        indexed inspect --verbose          # Detailed info about all collections
        indexed inspect my-collection --json
    """
    # Fetch collection info from core - this is connection-agnostic
    if name:
        # Inspect specific collection
        collections = inspect([name])
        
        # Check if collection exists and has valid data
        if not collections or collections[0].number_of_documents == 0:
            # Check if it truly doesn't exist vs just being empty
            all_collections = inspect()
            exists = any(c.name == name for c in all_collections)
            
            if not exists:
                console.print(f"\n[red]Collection '{name}' not found[/red]")
                if all_collections:
                    console.print("\n[dim]Available collections:[/dim]")
                    for coll in all_collections:
                        console.print(f"  • {coll.name}")
                console.print()
                raise typer.Exit(1)
        
        # Format and display single collection
        if json_output:
            format_collection_json(collections[0])
        else:
            format_collection_detail(collections[0])
    else:
        # List all collections
        collections = inspect()
        
        if not collections:
            console.print("\nNo collections found")
            console.print("\n[dim]Get started: indexed add[/dim]")
            return
        
        # Format and display list
        if json_output:
            format_collections_json(collections)
        else:
            format_collection_list(collections, verbose=verbose)


# For Typer command registration
app = typer.Typer(help="Inspect indexed collections")
app.command(name="inspect")(inspect_collections)
