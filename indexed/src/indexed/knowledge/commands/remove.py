"""Remove command for removing collections."""

from typing import Optional

import typer
from rich.prompt import Confirm
from rich.panel import Panel
from rich.console import Group

from core.v1 import Index
from core.v1.engine.services import inspect
from ...utils.console import console
from ...utils.components import (
    create_info_row,
    create_summary,
    get_card_border_style,
    get_card_padding,
    get_heading_style,
    get_error_style,
    get_accent_style,
    get_dim_style,
    get_default_style,
    print_success,
    print_error,
)
from ...utils.format import format_size, format_time

app = typer.Typer(help="Remove collections")


@app.command()
def remove(
    collection: str = typer.Argument(..., help="Collection name to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose (INFO) logging",
        rich_help_panel="Logging",
    ),
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Output logs as JSON (structured)",
        rich_help_panel="Logging",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Set logging level (DEBUG, INFO, WARNING, ERROR)",
        rich_help_panel="Logging",
    ),
):
    """Remove a collection from the index.

    Examples:
        indexed remove my-collection      # Remove with confirmation
        indexed remove my-collection -f   # Remove without confirmation
    """
    from ...utils.logging import setup_root_logger
    
    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger(level_str=effective_level, json_mode=json_logs)
    
    index = Index()

    # Fetch all collections to validate
    all_collections = inspect()

    if not all_collections:
        console.print("\n[dim]No collections found[/dim]")
        console.print("[dim]Create collections with: indexed index create[/dim]\n")
        return

    # Find the target collection
    target_collection = None
    for coll in all_collections:
        if coll.name == collection:
            target_collection = coll
            break

    if not target_collection:
        console.print(f"[red]Collection '{collection}' not found[/red]")
        if all_collections:
            console.print("\n[dim]Available collections:[/dim]")
            for coll in all_collections:
                console.print(f"  • {coll.name}")
        console.print()
        raise typer.Exit(1)

    # Show collection details
    console.print()
    console.print(
        f"[{get_heading_style()}]Removing [{get_accent_style()}]{collection}[/{get_accent_style()}] Collection:[/{get_heading_style()}]"
    )
    console.print()

    lines = []
    if target_collection.source_type:
        lines.append(create_info_row("Type", target_collection.source_type))
    if target_collection.relative_path:
        lines.append(create_info_row("Path", target_collection.relative_path))
    lines.append(
        create_info_row("Documents", str(target_collection.number_of_documents))
    )
    lines.append(create_info_row("Chunks", str(target_collection.number_of_chunks)))
    if target_collection.disk_size_bytes:
        lines.append(
            create_info_row("Size", format_size(target_collection.disk_size_bytes))
        )
    if target_collection.updated_time:
        lines.append(
            create_info_row("Updated", format_time(target_collection.updated_time))
        )

    content = Group(*lines)
    panel = Panel(
        content,
        title=f"[bold]{collection}[/bold]",
        title_align="left",
        border_style=get_card_border_style(),
        padding=get_card_padding(),
    )
    console.print(panel)

    # Show confirmation dialog
    if not force:
        console.print()
        console.print(
            f"[{get_heading_style()}]You are about to remove:[/{get_heading_style()}] {target_collection.number_of_documents} documents, {target_collection.number_of_chunks} chunks, {format_size(target_collection.disk_size_bytes)} size."
        )

        if not Confirm.ask(
            f"[{get_error_style()}]This action cannot be undone! Continue?[/{get_error_style()}]",
            default=False,
        ):
            console.print(f"[{get_dim_style()}]Cancelled[/{get_dim_style()}]")
            raise typer.Exit(0)

    # Execute removal
    try:
        console.print(
            f"[{get_dim_style()}]Removing collection '{collection}'...[/{get_dim_style()}]"
        )
        index.remove(collection)
        print_success(f"Collection '{collection}' removed")

        # Show summary
        console.print()
        console.print(create_summary("Removed", f"{collection} collection."))

    except Exception as e:
        print_error(f"Failed to remove '{collection}': {e}")
        raise typer.Exit(1)
