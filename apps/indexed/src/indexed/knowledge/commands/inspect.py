"""Inspect command - Show indexed collections or detailed info about a specific collection.

This command both fetches collection data (using the core inspect() service) AND
contains all formatter logic (previously in inspect_formatter.py) for displaying
with Rich or JSON. Presentation and command logic are now unified in this file.
"""

import typer
from typing import List, TYPE_CHECKING
from rich.columns import Columns

from ...utils.console import console
from ...utils.simple_output import is_simple_output, print_json
from ...utils.components import (
    create_info_card,
    create_detail_card,
    get_heading_style,
    get_dim_style,
    create_summary,
    print_error,
)

if TYPE_CHECKING:
    from core.v1.engine.services import CollectionInfo

# ---- Use format_size and format_time from @format.py ----
from ...utils.format import format_size, format_time


def _build_collection_rows(
    coll: "CollectionInfo", include_index: bool = False, include_created: bool = False
) -> list[tuple[str, str]]:
    """Build standard info rows for a collection.

    Centralizes row construction so all views (brief, verbose, detail)
    use the same labels and formatting.
    """
    rows = []
    rows.append(("Type", coll.source_type or "Unknown"))
    if coll.relative_path:
        rows.append(("Path", coll.relative_path))
    rows.append(("Documents", str(coll.number_of_documents)))
    rows.append(("Chunks", str(coll.number_of_chunks)))
    if coll.disk_size_bytes:
        rows.append(("Size", format_size(coll.disk_size_bytes)))
    if include_index and coll.index_size_bytes:
        rows.append(("Index", format_size(coll.index_size_bytes)))
    if include_created and coll.created_time:
        rows.append(("Created", format_time(coll.created_time)))
    if coll.updated_time:
        rows.append(("Updated", format_time(coll.updated_time)))
    return rows


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

        rows = _build_collection_rows(coll)
        card = create_info_card(title=coll.name, rows=rows)
        panels.append(card)

    if panels:
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
    count = len(collections)
    plural = "Collection" if count == 1 else "Collections"
    console.print(
        f"[{get_heading_style()}]{count} {plural} Details:[/{get_heading_style()}]"
    )
    console.print()

    total_docs = 0
    total_chunks = 0
    total_size = 0

    for coll in collections:
        total_docs += coll.number_of_documents
        total_chunks += coll.number_of_chunks
        if coll.disk_size_bytes:
            total_size += coll.disk_size_bytes

        rows = _build_collection_rows(coll, include_index=True, include_created=True)
        card = create_detail_card(title=coll.name, rows=rows)
        console.print(card)

    console.print()
    console.print(
        create_summary(
            "Total",
            f"{total_docs} documents, {total_chunks} chunks, {format_size(total_size)}",
        )
    )
    console.print()


def format_collection_detail(info: "CollectionInfo") -> None:
    """Display detailed information about a specific collection."""
    console.print()
    console.print(
        f"[{get_heading_style()}]{info.name} Collection Details:[/{get_heading_style()}]"
    )
    console.print()

    rows = _build_collection_rows(info, include_index=True, include_created=True)
    card = create_detail_card(title=info.name, rows=rows)
    console.print(card)
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
    print_json(output)


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
    print_json(output)


# ---- END FORMATTER LOGIC ----


def inspect_collections(
    name: str = typer.Argument(None, help="Collection name to inspect in detail"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show detailed information for all collections"
    ),
) -> None:
    """Show all indexed collections or inspect a specific collection.

    Examples:
        indexed inspect                            # List all collections
        indexed inspect my-collection              # Detailed info about specific collection
        indexed inspect --verbose                  # Detailed info about all collections
        indexed --simple-output inspect            # JSON output
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
                print_error(f"Collection '{name}' not found")
                if all_collections:
                    console.print(
                        f"\n[{get_dim_style()}]Available collections:[/{get_dim_style()}]"
                    )
                    for coll in all_collections:
                        console.print(f"  • {coll.name}")
                console.print()
                raise typer.Exit(1)

        # Format and display single collection
        if is_simple_output():
            format_collection_json(collections[0])
        else:
            format_collection_detail(collections[0])
    else:
        # List all collections (no progress bar)
        collections = inspect_svc()

        if not collections:
            console.print(
                f"\n[{get_dim_style()}]No collections found[/{get_dim_style()}]"
            )
            console.print(
                f"[{get_dim_style()}]Get started: indexed index create [source][/{get_dim_style()}]"
            )
            return

        # Format and display list
        if is_simple_output():
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
