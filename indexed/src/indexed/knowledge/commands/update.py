"""Update command for refreshing collections."""

import typer
from core.v1.engine.services import (
    update as update_service,
    SourceConfig,
    status as svc_status,
    inspect,
)
from ...utils.logging import is_verbose_mode
from ...utils.context_managers import NoOpContext, suppress_core_output
from ...utils.components.summary import create_summary
from ...utils.console import console
from ...utils.progress_bar import create_progress_update_callback
from ...utils.components.status import OperationStatus
from ...utils.components.theme import (
    get_heading_style,
    get_dim_style,
)
from ...utils.components import (
    create_detail_card,
    get_accent_style,
)

app = typer.Typer(help="Update collections")


def _format_source_type(source_type: str) -> str:
    """Format source type for display (e.g., 'jiraCloud' -> 'Jira Cloud')."""
    if not source_type:
        return "Unknown"
    
    type_map = {
        "jira": "Jira",
        "jiraCloud": "Jira Cloud",
        "confluence": "Confluence",
        "confluenceCloud": "Confluence Cloud",
        "localFiles": "Local Files",
    }
    return type_map.get(source_type, source_type.capitalize())


def _format_update_comparison(before, after):
    """Displays a comparison of metadata before and after the update using card format."""

    def format_change(before_val, after_val):
        """Format a value change with color coding."""
        if before_val is None or after_val is None:
            return f"{before_val} → {after_val}"

        delta = after_val - before_val
        if delta > 0:
            return f"{before_val} → {after_val} ([green]+{delta}[/green])"
        elif delta < 0:
            return f"{before_val} → {after_val} ([red]{delta}[/red])"
        else:
            return f"{before_val} → {after_val} [{get_dim_style()}](no change)[/{get_dim_style()}]"

    def format_size_change(before_bytes, after_bytes):
        """Format size change with proper units."""
        if before_bytes is None or after_bytes is None:
            return f"{before_bytes} → {after_bytes}"

        def format_bytes(bytes_val):
            if bytes_val is None:
                return "unknown"
            units = ["B", "KB", "MB", "GB", "TB"]
            size = float(bytes_val)
            for unit in units:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} PB"

        before_str = format_bytes(before_bytes)
        after_str = format_bytes(after_bytes)

        if before_bytes is not None and after_bytes is not None:
            delta = after_bytes - before_bytes
            if delta > 0:
                return f"{before_str} → {after_str} ([green]+{format_bytes(delta)}[/green])"
            elif delta < 0:
                return f"{before_str} → {after_str} ([red]{format_bytes(abs(delta))}[/red])"
            else:
                return f"{before_str} → {after_str} [{get_dim_style()}](no change)[/{get_dim_style()}]"

        return f"{before_str} → {after_str}"

    # Build info rows for the card
    rows = []

    # Collection name
    rows.append(("Collection", after.name))

    # Collection type
    if hasattr(after, "source_type") and after.source_type:
        rows.append(("Type", _format_source_type(after.source_type)))

    # Documents count
    if hasattr(before, "number_of_documents") and hasattr(after, "number_of_documents"):
        before_docs = getattr(before, "number_of_documents", 0)
        after_docs = getattr(after, "number_of_documents", 0)
        rows.append(("Documents", format_change(before_docs, after_docs)))

    # Chunks count
    if hasattr(before, "number_of_chunks") and hasattr(after, "number_of_chunks"):
        before_chunks = getattr(before, "number_of_chunks", 0)
        after_chunks = getattr(after, "number_of_chunks", 0)
        rows.append(("Chunks", format_change(before_chunks, after_chunks)))

    # Size change
    if hasattr(before, "disk_size_bytes") and hasattr(after, "disk_size_bytes"):
        before_size = getattr(before, "disk_size_bytes", None)
        after_size = getattr(after, "disk_size_bytes", None)
        rows.append(("Size", format_size_change(before_size, after_size)))

    # Updated time (human-readable)
    if hasattr(after, "updated_time") and after.updated_time:
        from indexed.utils.format import format_time

        readable_time = format_time(after.updated_time)
        rows.append(("Updated", readable_time))

    # Create card using the same component system as other commands
    card = create_detail_card(
        title="Updated Collection",
        rows=rows,
    )
    console.print(card)


@app.command()
def update(
    collection: str = typer.Argument(
        None, help="Collection name to update (omit to update all collections)"
    ),
):
    """Refresh and re-index a collection or all collections."""
    # Determine collections to update
    if collection is None:
        # Update all collections
        all_statuses = svc_status()
        if not all_statuses:
            console.print("\nNo collections found to update")
            return

        collections_to_update = [s.name for s in all_statuses]
        console.print(
            f"\n[{get_heading_style()}]Updating {len(collections_to_update)} Collections:[/{get_heading_style()}]"
        )
    else:
        # Update specific collection
        statuses = svc_status([collection])
        if not statuses:
            typer.echo(f"❌ Collection '{collection}' not found")
            raise typer.Exit(1)

        collections_to_update = [collection]
        console.print(
            f"\n[{get_heading_style()}]Updating 1 Collection:[/{get_heading_style()}]"
        )

    # Capture before state for all collections
    before_data = {}
    for coll_name in collections_to_update:
        before_data[coll_name] = inspect([coll_name])[0]

    # Update each collection with individual progress
    update_error = None
    for coll_name in collections_to_update:
        # Get collection status to build proper SourceConfig
        coll_status = svc_status([coll_name])[0]
        config = SourceConfig(
            name=coll_name,
            type="localFiles",  # Default type, not used in update
            base_url_or_path="",  # Not used in update
            indexer=coll_status.indexers[0],  # Get from collection status
        )

        if is_verbose_mode():
            # Verbose mode: show core logs directly
            with NoOpContext():
                update_service([config])
        else:
            # Normal mode: use OperationStatus for live updates
            console.print()
            with OperationStatus(console, f"Updating {coll_name}", capture_logs=False) as status:
                # Show initial status with force_render to ensure spinner is visible
                status.update("Checking for updates...", force_render=True)
                callback = create_progress_update_callback(status)
                try:
                    with suppress_core_output():
                        update_service([config], progress_callback=callback)
                    status.complete(
                        success=True,
                        success_message=f"✓ [{get_accent_style()}]{coll_name}[/{get_accent_style()}]: Updated",
                    )
                except Exception as e:
                    status.complete(
                        success=False,
                        failure_message=f"✗ [{get_accent_style()}]{coll_name}[/{get_accent_style()}]: Update Failed",
                    )
                    update_error = e
                    break
    
    # If update failed, show error and exit
    if update_error:
        typer.secho(f"✗ Failed to update collection: {str(update_error)}", fg="red", err=True)
        raise typer.Exit(1)

    # Display comparison results
    console.print(
        f"\n[{get_heading_style()}]Updated Collection Details:[/{get_heading_style()}] \n"
    )

    total_docs = 0
    total_chunks = 0
    docs_delta = 0
    chunks_delta = 0

    for coll_name in collections_to_update:
        after_info = inspect([coll_name])[0]
        before_info = before_data[coll_name]
        
        total_docs += after_info.number_of_documents
        total_chunks += after_info.number_of_chunks
        docs_delta += after_info.number_of_documents - before_info.number_of_documents
        chunks_delta += after_info.number_of_chunks - before_info.number_of_chunks
        
        _format_update_comparison(before_info, after_info)

    # Generate dynamic summary based on changes
    num_collections = len(collections_to_update)
    coll_word = "Collection" if num_collections == 1 else "Collections"
    
    if docs_delta == 0 and chunks_delta == 0:
        # No changes
        result_text = f"Checked {num_collections} {coll_word} - all up to date ({total_docs} documents, {total_chunks} chunks)"
    else:
        # Build change description
        changes = []
        if docs_delta > 0:
            changes.append(f"+{docs_delta} documents")
        elif docs_delta < 0:
            changes.append(f"{docs_delta} documents")
        
        if chunks_delta > 0:
            changes.append(f"+{chunks_delta} chunks")
        elif chunks_delta < 0:
            changes.append(f"{chunks_delta} chunks")
        
        change_str = ", ".join(changes) if changes else "metadata updated"
        result_text = f"Updated {num_collections} {coll_word}: {change_str} (now {total_docs} documents, {total_chunks} chunks)"

    # Summary
    console.print()
    summary = create_summary("Result", result_text)
    console.print(summary)
    console.print()
