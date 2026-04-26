"""Remove command for removing collections."""

from typing import Optional, TYPE_CHECKING

import typer
from rich.prompt import Confirm

if TYPE_CHECKING:
    pass

from ...utils.console import console
from ...utils.components import (
    create_detail_card,
    create_summary,
    get_heading_style,
    get_error_style,
    get_accent_style,
    get_dim_style,
    print_success,
    print_error,
)
from ...utils.format import format_size, format_time, format_source_type
from ...utils.simple_output import is_simple_output, print_json
from ...utils.logging import is_verbose_mode
from ...utils.progress_bar import create_phased_progress, build_progress_title
from ...utils.context_managers import NoOpContext
from ...utils.storage_info import display_storage_mode_for_command

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
    # Use module-level lazy-loaded services (supports mocking in tests)
    from . import remove as this_module

    index_svc = this_module.Index
    inspect_svc = this_module.inspect
    setup_root_logger_svc = this_module.setup_root_logger

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger_svc(level_str=effective_level, json_mode=json_logs)

    index = index_svc()
    simple = is_simple_output()

    # Display storage mode indicator (not in verbose/simple mode, to keep logs clean)
    if not is_verbose_mode() and not simple:
        from indexed_config import ConfigService

        ConfigService.instance()
        display_storage_mode_for_command(console)

    # Fetch all collections to validate
    all_collections = inspect_svc()

    if not all_collections:
        console.print(f"\n[{get_dim_style()}]No collections found[/{get_dim_style()}]")
        console.print(
            f"[{get_dim_style()}]Get started: indexed index create [source][/{get_dim_style()}]"
        )
        return

    # Find the target collection
    target_collection = None
    for coll in all_collections:
        if coll.name == collection:
            target_collection = coll
            break

    if not target_collection:
        print_error(f"Collection '{collection}' not found")
        if all_collections:
            console.print(
                f"\n[{get_dim_style()}]Available collections:[/{get_dim_style()}]"
            )
            for coll in all_collections:
                console.print(f"  • {coll.name}")
        console.print()
        raise typer.Exit(1)

    # Simple output mode: skip confirmation, output JSON
    if simple:
        try:
            index.remove(collection)
            print_json({"status": "removed", "collection": collection})
        except Exception as e:
            print_json({"status": "error", "collection": collection, "error": str(e)})
            raise typer.Exit(1)
        return

    # Show collection details
    console.print()
    console.print(
        f"[{get_heading_style()}]Removing [{get_accent_style()}]{collection}[/{get_accent_style()}] Collection:[/{get_heading_style()}]"
    )
    console.print()

    rows = []
    if target_collection.source_type:
        rows.append(("Type", target_collection.source_type))
    if target_collection.relative_path:
        rows.append(("Path", target_collection.relative_path))
    rows.append(("Documents", str(target_collection.number_of_documents)))
    rows.append(("Chunks", str(target_collection.number_of_chunks)))
    if target_collection.disk_size_bytes:
        rows.append(("Size", format_size(target_collection.disk_size_bytes)))
    if target_collection.updated_time:
        rows.append(("Updated", format_time(target_collection.updated_time)))

    card = create_detail_card(title=collection, rows=rows)
    console.print(card)

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
        if is_verbose_mode():
            # Verbose mode: show all logs, no progress UI
            with NoOpContext():
                index.remove(collection)
        else:
            # Normal mode: phased progress display
            source_type = target_collection.source_type
            source_display = format_source_type(source_type) if source_type else ""
            title = build_progress_title("Removing", collection, source_display)

            with create_phased_progress(title=title) as phased:
                phased.start_phase("Removing collection data")
                index.remove(collection)
                phased.finish_phase("Removing collection data")

        console.print()
        print_success(f"Collection '{collection}' removed")

        # Show summary
        console.print()
        console.print(create_summary("Removed", f"{collection} collection."))

    except Exception as e:
        print_error(f"Failed to remove '{collection}': {e}")
        raise typer.Exit(1)


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "Index":
        from core.v1 import Index

        return Index
    elif name == "inspect":
        from core.v1.engine.services import inspect

        return inspect
    elif name == "setup_root_logger":
        from ...utils.logging import setup_root_logger

        return setup_root_logger
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
