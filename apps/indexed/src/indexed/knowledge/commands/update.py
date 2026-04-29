"""Update command for refreshing collections."""

from typing import Optional

import typer

from indexed_config import ConfigService
from ...utils.logging import is_verbose_mode
from ...utils.simple_output import is_simple_output, print_json
from ...utils.context_managers import NoOpContext
from ...utils.components.summary import create_summary
from ...utils.console import console
from ...utils.progress_bar import create_phased_progress
from ...utils.components.theme import (
    get_heading_style,
    get_dim_style,
    get_success_style,
    get_error_style,
)
from ...utils.components import (
    create_detail_card,
    print_success,
    print_error,
    print_info,
)
from ...utils.credentials import ensure_credentials_for_source
from ...utils.format import format_source_type as _format_source_type

app = typer.Typer(help="Update collections")


def _read_manifest_reader_config(collection_name: str) -> dict:
    """Read the reader dict from a collection manifest; return {} on failure."""
    try:
        import json
        from pathlib import Path
        from core.v1.config_models import get_default_collections_path

        manifest_path = (
            Path(get_default_collections_path()) / collection_name / "manifest.json"
        )
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            return manifest.get("reader", {})
    except Exception:
        pass
    return {}


def _display_collection_update_header(
    coll_name: str, source_type: str | None, reader_config: dict
) -> None:
    """Print the per-collection heading block before progress bars."""
    from ...utils.components.info_row import create_info_row
    from ...utils.format import format_path_tilde
    from ...utils.files_source_display import build_excluded_row_text
    from connectors.files.schema import DEFAULT_EXCLUDED_DIRS

    heading = get_heading_style()
    console.print(f'\n[{heading}]Updating Collection "{coll_name}"[/{heading}]')

    if source_type:
        console.print(create_info_row("Type", _format_source_type(source_type)))

    if source_type == "localFiles" and reader_config:
        path = str(reader_config.get("basePath", ""))
        console.print(create_info_row("Path", format_path_tilde(path)))

        include_patterns: list[str] = reader_config.get("includePatterns") or ["*"]
        positive = [p for p in include_patterns if not p.startswith("!")]
        patterns_display = "* (all files)" if positive == ["*"] else ", ".join(positive)
        console.print(create_info_row("Included Patterns", patterns_display))

        _dirs = reader_config.get("excludedDirs")
        excluded_dirs: list[str] = (
            _dirs if isinstance(_dirs, list) else list(DEFAULT_EXCLUDED_DIRS)
        )
        respect_gitignore: bool = reader_config.get("respectGitignore", True)
        console.print(
            create_info_row(
                "Excluded",
                build_excluded_row_text(
                    path, include_patterns, excluded_dirs, respect_gitignore
                ),
            )
        )

    console.print()


def _config_existed_before(config_service: ConfigService) -> bool:
    """
    Determine whether a configuration file existed prior to an operation based on the ConfigService's resolved storage mode.

    Returns:
        bool: `True` if a local config file exists when storage mode is "local", or `True` if a global config file exists when storage mode is not "local"; `False` otherwise.
    """
    storage_mode = config_service.resolve_storage_mode()
    if storage_mode == "local":
        return config_service.store.has_local_config()
    else:
        return config_service.store.has_global_config()


def _get_config_path(config_service: ConfigService) -> str:
    """
    Return the path to the active configuration file based on the resolved storage mode.

    Parameters:
        config_service (ConfigService): Service used to determine storage mode and access configured paths.

    Returns:
        str: The configuration file path — the workspace path when storage mode is "local", otherwise the global path.
    """
    storage_mode = config_service.resolve_storage_mode()
    if storage_mode == "local":
        return str(config_service.store.workspace_path)
    else:
        return str(config_service.store.global_path)


def _format_update_comparison(before, after):
    """
    Display a detail card comparing collection metadata before and after an update.

    Parameters:
        before: An object representing the collection state prior to the update. Expected attributes (when present) include
            `name`, `source_type`, `number_of_documents`, `number_of_chunks`, `disk_size_bytes`, and `updated_time`.
        after: An object representing the collection state after the update. Expected attributes match those of `before`.

    Description:
        Prints a formatted "Updated Collection" detail card to the console containing any of the following rows when data
        is available: Collection name, Type (friendly display of `source_type`), Documents (with delta), Chunks (with delta),
        Size (human-readable bytes with delta), and Updated (human-readable timestamp). Missing attributes are omitted.
    """

    def format_change(before_val, after_val):
        """Format a value change with color coding."""
        if before_val is None or after_val is None:
            return f"{before_val} → {after_val}"

        success = get_success_style()
        error = get_error_style()
        dim = get_dim_style()
        delta = after_val - before_val
        if delta > 0:
            return f"{before_val} → {after_val} ([{success}]+{delta}[/{success}])"
        elif delta < 0:
            return f"{before_val} → {after_val} ([{error}]{delta}[/{error}])"
        else:
            return f"{before_val} → {after_val} [{dim}](no change)[/{dim}]"

    def format_size_change(before_bytes, after_bytes):
        """Format size change with proper units."""
        from indexed.utils.format import format_size

        if before_bytes is None or after_bytes is None:
            return f"{before_bytes} → {after_bytes}"

        before_str = format_size(before_bytes)
        after_str = format_size(after_bytes)
        success = get_success_style()
        error = get_error_style()
        dim = get_dim_style()
        delta = after_bytes - before_bytes
        if delta > 0:
            return f"{before_str} → {after_str} ([{success}]+{format_size(delta)}[/{success}])"
        elif delta < 0:
            return f"{before_str} → {after_str} ([{error}]{format_size(abs(delta))}[/{error}])"
        else:
            return f"{before_str} → {after_str} [{dim}](no change)[/{dim}]"

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
    """Refresh and re-index a collection or all collections."""
    # Use module-level lazy-loaded services (supports mocking in tests)
    from . import update as this_module

    update_service = this_module.update_service
    source_config_class = this_module.SourceConfig
    svc_status = this_module.svc_status
    inspect_svc = this_module.inspect
    setup_root_logger_svc = this_module.setup_root_logger

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger_svc(level_str=effective_level, json_mode=json_logs)

    # Initialize ConfigService and check if config existed before
    config_service = ConfigService.instance()
    config_existed = _config_existed_before(config_service)

    simple = is_simple_output()

    # Display storage mode indicator (not in verbose/simple mode, to keep logs clean)
    if not is_verbose_mode() and not simple:
        from ...utils.storage_info import display_storage_mode_for_command

        display_storage_mode_for_command(console)

    # Determine collections to update
    if collection is None:
        # Update all collections
        all_statuses = svc_status()
        if not all_statuses:
            if simple:
                print_json({"error": "No collections found"})
                return
            console.print(
                f"\n[{get_dim_style()}]No collections found to update[/{get_dim_style()}]"
            )
            console.print(
                f"[{get_dim_style()}]Get started: indexed index create [source][/{get_dim_style()}]"
            )
            return

        collections_to_update = [s.name for s in all_statuses]
        if not simple and len(collections_to_update) > 1:
            names = ", ".join(f'"{n}"' for n in collections_to_update)
            console.print(
                f"\n[{get_heading_style()}]Updating {len(collections_to_update)} Collections: {names}[/{get_heading_style()}]"
            )
    else:
        # Update specific collection
        statuses = svc_status([collection])
        if not statuses:
            if simple:
                print_json(
                    {"status": "error", "error": f"Collection '{collection}' not found"}
                )
            else:
                print_error(f"Collection '{collection}' not found")
            raise typer.Exit(1)

        collections_to_update = [collection]

    # Capture before state for all collections
    before_data = {}
    for coll_name in collections_to_update:
        inspect_result = inspect_svc([coll_name])
        if not inspect_result:
            msg = f"Cannot inspect collection '{coll_name}' before update"
            if simple:
                print_json({"status": "error", "error": msg})
            else:
                print_error(msg)
            raise typer.Exit(1)
        before_data[coll_name] = inspect_result[0]

    # Update each collection with individual progress
    update_error = None
    config_was_created = False
    updated_collections = []
    successfully_updated: list[str] = []
    total_docs = 0
    total_chunks = 0
    docs_delta = 0
    chunks_delta = 0

    for coll_name in collections_to_update:
        # Get collection status to build proper SourceConfig
        coll_statuses = svc_status([coll_name])
        if not coll_statuses:
            print_error(f"Collection '{coll_name}' not found during update")
            continue
        coll_status = coll_statuses[0]

        # Ensure credentials are available for this source type
        source_type = getattr(coll_status, "source_type", None)
        if source_type:
            ensure_credentials_for_source(source_type, config_service)

        if not coll_status.indexers:
            print_error(f"Collection '{coll_name}' has no indexers configured")
            continue

        source_config = source_config_class(
            name=coll_name,
            type="localFiles",  # Default type, not used in update
            base_url_or_path="",  # Not used in update
            indexer=coll_status.indexers[0],  # Get from collection status
        )

        if simple or is_verbose_mode():
            # Simple output / verbose mode: no progress display
            try:
                with NoOpContext():
                    update_service([source_config])
                successfully_updated.append(coll_name)
            except Exception as e:
                if not simple:
                    print_error(f"Failed to update collection '{coll_name}': {str(e)}")
                update_error = e
                break
        else:
            reader_cfg = _read_manifest_reader_config(coll_name)
            _display_collection_update_header(coll_name, source_type, reader_cfg)

            _coll_error: Exception | None = None
            with create_phased_progress(title=None) as phased:
                try:
                    update_service([source_config], phased_progress=phased)
                except Exception as e:
                    _coll_error = e

            console.print()
            if _coll_error is None:
                after_result = inspect_svc([coll_name])
                if after_result:
                    after_info = after_result[0]
                    before_info = before_data[coll_name]
                    _format_update_comparison(before_info, after_info)
                    total_docs += after_info.number_of_documents
                    total_chunks += after_info.number_of_chunks
                    docs_delta += (
                        after_info.number_of_documents - before_info.number_of_documents
                    )
                    chunks_delta += (
                        after_info.number_of_chunks - before_info.number_of_chunks
                    )
                    updated_collections.append(
                        {
                            "name": coll_name,
                            "documents": after_info.number_of_documents,
                            "chunks": after_info.number_of_chunks,
                            "documents_delta": after_info.number_of_documents
                            - before_info.number_of_documents,
                            "chunks_delta": after_info.number_of_chunks
                            - before_info.number_of_chunks,
                        }
                    )
                console.print()
                print_success(f"Collection '{coll_name}' updated")
                console.print()
            else:
                print_error(f"Collection '{coll_name}' update failed")
                update_error = _coll_error
                break

    # If update failed, show error and exit
    if update_error:
        if simple:
            print_json(
                {"status": "error", "error": f"Failed to update: {str(update_error)}"}
            )
        else:
            print_error(f"Failed to update collection: {str(update_error)}")
        raise typer.Exit(1)

    # Check if config was created during updates
    if not config_existed:
        config_was_created = _config_existed_before(config_service)

    # Notify user if config was newly created
    if not config_existed and config_was_created and not simple:
        config_path = _get_config_path(config_service)
        console.print()
        print_info(f"Created new config file with default settings: {config_path}")

    # Simple output mode: JSON status
    if simple:
        for coll_name in successfully_updated:
            inspect_result = inspect_svc([coll_name])
            if inspect_result:
                after_info = inspect_result[0]
                before_info = before_data[coll_name]
                total_docs += after_info.number_of_documents
                total_chunks += after_info.number_of_chunks
                updated_collections.append(
                    {
                        "name": coll_name,
                        "documents": after_info.number_of_documents,
                        "chunks": after_info.number_of_chunks,
                        "documents_delta": after_info.number_of_documents
                        - before_info.number_of_documents,
                        "chunks_delta": after_info.number_of_chunks
                        - before_info.number_of_chunks,
                    }
                )
        print_json(
            {
                "status": "updated",
                "collections": updated_collections,
                "total_documents": total_docs,
                "total_chunks": total_chunks,
            }
        )
        return

    # Result summary for multiple collections (not shown in verbose mode — logs cover it)
    if len(collections_to_update) > 1 and not is_verbose_mode():
        num_collections = len(collections_to_update)
        if docs_delta == 0 and chunks_delta == 0:
            result_text = f"Checked {num_collections} Collections - all up to date ({total_docs} documents, {total_chunks} chunks)"
        else:
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
            result_text = f"Updated {num_collections} Collections: {change_str} (now {total_docs} documents, {total_chunks} chunks)"

        summary = create_summary("Result", result_text)
        console.print(summary)
        console.print()


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "update_service":
        from core.v1.engine.services import update

        return update
    elif name == "SourceConfig":
        from core.v1.engine.services import SourceConfig

        return SourceConfig
    elif name == "svc_status":
        from core.v1.engine.services import status

        return status
    elif name == "inspect":
        from core.v1.engine.services import inspect

        return inspect
    elif name == "setup_root_logger":
        from ...utils.logging import setup_root_logger

        return setup_root_logger
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
