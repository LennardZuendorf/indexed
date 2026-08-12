"""Remove command for removing collections."""

from typing import Callable, Optional, TYPE_CHECKING

import typer
from rich.markup import escape
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
    print_warning,
)
from ...utils.format import format_size, format_time, format_source_type
from ...utils.simple_output import is_simple_output, print_json
from ...utils.logging import is_verbose_mode
from ...utils.progress_bar import create_phased_progress, build_progress_title
from ...utils.context_managers import NoOpContext

app = typer.Typer(help="Remove collections")


def _remove_corrupt_collection(
    collection: str,
    collections_path: str,
    simple: bool,
    force: bool,
    clear_svc: Callable[..., None],
) -> None:
    """Remove a collection that exists on disk but is unreadable/corrupt.

    ``inspect()`` OMITS collections whose manifest can't be parsed (foundation/6
    E1), so the normal name lookup above never finds them — but the directory
    still occupies disk space, and a user must still be able to remove/recover
    it (foundation/6 regression fix). There is no valid metadata to show here,
    so this path skips the detail card and goes straight to confirm-then-delete.
    """
    if simple:
        try:
            clear_svc([collection], collections_path=collections_path)
            print_json(
                {
                    "status": "removed",
                    "collection": collection,
                    "note": "collection was corrupt/unreadable",
                }
            )
        except Exception as e:
            print_json({"status": "error", "collection": collection, "error": str(e)})
            raise typer.Exit(1)
        return

    print_warning(f"Collection '{collection}' is present but corrupt/unreadable")

    if not force:
        if not Confirm.ask(
            f"[{get_error_style()}]This action cannot be undone! Remove it anyway?[/{get_error_style()}]",
            default=False,
        ):
            console.print(f"[{get_dim_style()}]Cancelled[/{get_dim_style()}]")
            raise typer.Exit(0)

    try:
        clear_svc([collection], collections_path=collections_path)
        console.print()
        print_success(f"Collection '{collection}' removed")
    except Exception as e:
        print_error(f"Failed to remove '{collection}': {e}")
        raise typer.Exit(1)


@app.command()
def remove(
    ctx: typer.Context,
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
    from indexed.cli.composition import resolve_collections_context

    clear_svc = this_module.clear
    inspect_svc = this_module.inspect
    collection_exists_svc = this_module.collection_exists
    setup_root_logger_svc = this_module.setup_root_logger

    cli_ctx = resolve_collections_context()
    collections_path = str(cli_ctx.collections_path)

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger_svc(level_str=effective_level, json_mode=json_logs)

    simple = is_simple_output()

    # Fetch all collections to validate
    all_collections = inspect_svc(collections_path=collections_path)

    # Find the target collection
    target_collection = None
    for coll in all_collections:
        if coll.name == collection:
            target_collection = coll
            break

    if target_collection is None:
        # inspect() OMITS collections whose manifest can't be read (foundation/6
        # E1) — but a directory that still exists on disk, corrupt or not,
        # must remain removable. Fall back to a raw existence check before
        # reporting "not found" (foundation/6 regression fix).
        if collection_exists_svc(collection, collections_path=collections_path):
            _remove_corrupt_collection(
                collection, collections_path, simple, force, clear_svc
            )
            return

        if not all_collections:
            console.print(
                f"\n[{get_dim_style()}]No collections found[/{get_dim_style()}]"
            )
            console.print(
                f"[{get_dim_style()}]Get started: indexed index create [source][/{get_dim_style()}]"
            )
            return

        print_error(f"Collection '{collection}' not found")
        console.print(
            f"\n[{get_dim_style()}]Available collections:[/{get_dim_style()}]"
        )
        for coll in all_collections:
            console.print(f"  • {escape(coll.name)}")
        console.print()
        raise typer.Exit(1)

    # Simple output mode: skip confirmation, output JSON
    if simple:
        try:
            clear_svc([collection], collections_path=collections_path)
            print_json({"status": "removed", "collection": collection})
        except Exception as e:
            print_json({"status": "error", "collection": collection, "error": str(e)})
            raise typer.Exit(1)
        return

    # Show collection details
    console.print()
    console.print(
        f"[{get_heading_style()}]Removing [{get_accent_style()}]{escape(collection)}[/{get_accent_style()}] Collection:[/{get_heading_style()}]"
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
                clear_svc([collection], collections_path=collections_path)
        else:
            # Normal mode: phased progress display
            source_type = target_collection.source_type
            source_display = format_source_type(source_type) if source_type else ""
            title = build_progress_title("Removing", collection, source_display)

            with create_phased_progress(title=title) as phased:
                phased.start_phase("Removing collection data")
                clear_svc([collection], collections_path=collections_path)
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
    if name == "clear":
        from indexed.core.v1.engine import clear

        return clear
    elif name == "inspect":
        from indexed.core.v1.engine import inspect

        return inspect
    elif name == "collection_exists":
        from indexed.core.v1.engine import collection_exists

        return collection_exists
    elif name == "setup_root_logger":
        from ...utils.logging import setup_root_logger

        return setup_root_logger
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
