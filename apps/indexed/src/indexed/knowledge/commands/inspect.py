"""Inspect command - Show indexed collections or detailed info about a specific collection.

This command both fetches collection data (using the core inspect() service) AND
contains all formatter logic (previously in inspect_formatter.py) for displaying
with Rich or JSON. Presentation and command logic are now unified in this file.
"""

import typer
import json
from typing import List, TYPE_CHECKING
from rich.panel import Panel
from rich.console import Group
from rich.columns import Columns

from ...utils.console import console
from ...utils.components import (
    create_info_row,
    get_card_border_style,
    get_card_padding,
    get_detail_card_width,
    get_heading_style,
    create_summary,
)

if TYPE_CHECKING:
    from core.v1.engine.services import CollectionInfo

# ---- Use format_size and format_time from @format.py ----
from ...utils.format import format_size, format_time


def format_collection_list(
    collections: List["CollectionInfo"], verbose: bool = False
) -> None:
    """Display a list of collections with optional verbose detail."""
    if verbose:
        _show_verbose_list(collections)
    else:
        _show_brief_list(collections)


def _show_brief_list(collections: List["CollectionInfo"]) -> None:
    """Show minimal collection info in compact cards."""
    console.print()
    # Headline showing number of collections
    count = len(collections)
    plural = "Collection" if count == 1 else "Collections"
    console.print(
        f"[{get_heading_style()}]{count} {plural} Details:[/{get_heading_style()}]"
    )
    console.print()

    panels = []
    total_docs = 0
    total_chunks = 0

    for coll in collections:
        total_docs += coll.number_of_documents
        total_chunks += coll.number_of_chunks

        lines = []
        lines.append(create_info_row("Type", coll.source_type or "Unknown"))
        if coll.relative_path:
            lines.append(create_info_row("Path", coll.relative_path))
        lines.append(create_info_row("Documents", str(coll.number_of_documents)))
        lines.append(create_info_row("Chunks", str(coll.number_of_chunks)))
        if coll.disk_size_bytes:
            lines.append(create_info_row("Size", format_size(coll.disk_size_bytes)))
        lines.append(create_info_row("Updated", format_time(coll.updated_time)))

        content = Group(*lines)

        # Wrap in panel with consistent styling
        panel = Panel(
            content,
            title=f"[bold]{coll.name}[/bold]",
            title_align="left",
            border_style=get_card_border_style(),
            padding=get_card_padding(),
        )
        panels.append(panel)

    if len(panels) > 0:
        console.print(Columns(panels, equal=True, expand=True))

    # Summary

    console.print()
    console.print(
        create_summary("Total", f"{total_docs} documents, {total_chunks} chunks")
    )
    console.print()


def _show_verbose_list(collections: List["CollectionInfo"]) -> None:
    """Show detailed collection info for all collections with unified design."""
    console.print()
    # Headline showing number of collections
    count = len(collections)
    plural = "Collection" if count == 1 else "Collections"
    console.print(
        f"[{get_heading_style()}]{count} {plural} Exist:[/{get_heading_style()}]"
    )
    console.print()

    total_docs = 0
    total_chunks = 0
    total_size = 0

    for i, coll in enumerate(collections):
        if i > 0:
            console.print()  # Space between collections

        total_docs += coll.number_of_documents
        total_chunks += coll.number_of_chunks
        if coll.disk_size_bytes:
            total_size += coll.disk_size_bytes

        # Create content using consistent info rows
        lines = [
            create_info_row("Type", coll.source_type or "Unknown"),
        ]
        if coll.relative_path:
            lines.append(create_info_row("Path", coll.relative_path))
        lines.append(create_info_row("Documents", str(coll.number_of_documents)))
        lines.append(create_info_row("Chunks", str(coll.number_of_chunks)))
        if coll.disk_size_bytes:
            lines.append(create_info_row("Size", format_size(coll.disk_size_bytes)))
        lines.append(create_info_row("Updated", format_time(coll.updated_time)))

        content = Group(*lines)

        # Create panel for collection
        panel = Panel(
            content,
            title=f"[bold]{coll.name}[/bold]",
            title_align="left",
            border_style=get_card_border_style(),
            padding=get_card_padding(),
        )
        console.print(panel)

    console.print()
    console.print(
        create_summary(
            f"{count} {plural}",
            f"{total_docs} total documents, {total_chunks} total chunks, {format_size(total_size)} size.",
        )
    )
    console.print()


def format_collection_detail(info: "CollectionInfo") -> None:
    """Display detailed information about a specific collection."""
    console.print()
    # Headline showing collection name
    console.print(
        f"[{get_heading_style()}]{info.name} Collection Details:[/{get_heading_style()}]"
    )
    console.print()
    # Build content using consistent info rows
    lines = []
    if info.source_type:
        lines.append(create_info_row("Type", info.source_type))
    if info.relative_path:
        lines.append(create_info_row("Path", info.relative_path))
    lines.append(create_info_row("Docs", str(info.number_of_documents)))
    lines.append(create_info_row("Chunks", str(info.number_of_chunks)))
    if info.disk_size_bytes:
        lines.append(create_info_row("Size", format_size(info.disk_size_bytes)))
    if info.index_size_bytes:
        lines.append(create_info_row("Index", format_size(info.index_size_bytes)))
    if info.created_time:
        lines.append(create_info_row("Created", format_time(info.created_time)))
    if info.updated_time:
        lines.append(create_info_row("Updated", format_time(info.updated_time)))
    content = Group(*lines)
    panel = Panel(
        content,
        title=f"[bold]{info.name}[/bold]",
        title_align="left",
        border_style=get_card_border_style(),
        padding=get_card_padding(),
        width=get_detail_card_width(),
    )
    console.print(panel)
    console.print()


def format_collection_json(info: "CollectionInfo") -> None:
    """Display collection info as JSON."""
    output = {
        "name": info.name,
        "source_type": info.source_type,
        "path": info.relative_path,
        "number_of_documents": info.number_of_documents,
        "number_of_chunks": info.number_of_chunks,
        "disk_size_bytes": info.disk_size_bytes,
        "index_size_bytes": info.index_size_bytes,
        "created_time": info.created_time,
        "updated_time": info.updated_time,
    }
    console.print(json.dumps(output, indent=2))


def format_collections_json(collections: List["CollectionInfo"]) -> None:
    """Display a list of collections in JSON."""
    output = [
        {
            "name": c.name,
            "source_type": c.source_type,
            "path": c.relative_path,
            "number_of_documents": c.number_of_documents,
            "number_of_chunks": c.number_of_chunks,
            "disk_size_bytes": c.disk_size_bytes,
            "index_size_bytes": c.index_size_bytes,
            "created_time": c.created_time,
            "updated_time": c.updated_time,
        }
        for c in collections
    ]
    console.print(json.dumps(output, indent=2))


# ---- END FORMATTER LOGIC ----


def inspect_collections(
    name: str = typer.Argument(None, help="Collection name to inspect in detail"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed information for all collections"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show all indexed collections or inspect a specific collection.

    Examples:
        indexed inspect                    # List all collections
        indexed inspect my-collection      # Detailed info about specific collection
        indexed inspect --verbose          # Detailed info about all collections
        indexed inspect my-collection --json
    """
    # Use module-level lazy-loaded services (supports mocking in tests)
    from . import inspect as this_module

    inspect_svc = this_module.inspect

    # Fetch collection info from core - this is connection-agnostic
    if name:
        # Inspect specific collection (no progress bar)
        collections = inspect_svc([name])

        # Check if collection exists and has valid data
        if not collections or collections[0].number_of_documents == 0:
            # Check if it truly doesn't exist vs just being empty
            all_collections = inspect_svc()
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
        # List all collections (no progress bar)
        collections = inspect_svc()

        if not collections:
            console.print("\nNo collections found")
            console.print("\n[dim]Get started: indexed index create [source][/dim]")
            return

        # Format and display list
        if json_output:
            format_collections_json(collections)
        else:
            format_collection_list(collections, verbose=verbose)


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "inspect":
        from core.v1.engine.services import inspect

        return inspect
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# For Typer command registration
app = typer.Typer(help="Inspect indexed collections")
app.command(name="inspect")(inspect_collections)
