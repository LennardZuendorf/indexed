"""Update command for refreshing collections."""

from typing import Any, Optional

import typer

from indexed.config import ConfigService
from ...utils.logging import is_verbose_mode
from ...utils.simple_output import is_simple_output, print_json
from ...utils.context_managers import NoOpContext
from ...utils.components.summary import create_summary
from ...utils.console import console
from ...utils.progress_bar import create_phased_progress
from ...utils.components import print_error, print_info
from ...utils.credentials import ensure_credentials_for_source
from ...utils.format import format_source_type as _format_source_type

# Public/test surface: the Typer app + command, plus the helpers the test suite
# imports directly. ``_format_source_type`` is re-exported here (the renderer
# that used it now lives in update_service) — listing it keeps that intentional.
__all__ = [
    "app",
    "update",
    "_config_existed_before",
    "_get_config_path",
    "_format_update_comparison",
    "_format_source_type",
]

app = typer.Typer(help="Update collections")


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
    """Render the before/after comparison card.

    Thin wrapper over ``update_service.format_update_comparison`` that injects
    *this* module's ``console`` so unit tests patching ``update.console`` (and
    the loop's own patched console) still capture the print. The rendering impl
    moved to update_service (thin command, fat service — mirrors search_render).
    """
    from . import update_service as svc

    svc.format_update_comparison(before, after, console=console)


@app.command()
def update(
    ctx: typer.Context,
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
    # Use module-level lazy-loaded services (supports mocking in tests). The
    # loop/aggregation live in update_service; it reaches these same seams back
    # through ``this_module`` so tests keep patching one place (foundation E8).
    from . import update as this_module
    from . import update_service as svc

    setup_root_logger_svc = this_module.setup_root_logger

    from ...composition import wiring_kwargs_for_update
    from indexed.cli.composition import resolve_collections_context

    mode_override = ctx.obj.get("mode_override") if ctx.obj else None
    cli_ctx = resolve_collections_context(mode_override=mode_override)
    update_wiring = wiring_kwargs_for_update(cli_ctx)
    collections_path = str(cli_ctx.collections_path)
    config_service = cli_ctx.config_service

    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger_svc(level_str=effective_level, json_mode=json_logs)

    # Check if config existed before
    config_existed = _config_existed_before(config_service)

    simple = is_simple_output()

    # Display storage mode indicator (not in verbose/simple mode, to keep logs clean)
    if not is_verbose_mode() and not simple:
        from ...utils.storage_info import display_storage_mode_for_command

        display_storage_mode_for_command(console)

    # Resolve collections + capture before-state (thin command: parse + delegate)
    collections_to_update = svc.resolve_collections_to_update(
        this_module,
        collection=collection,
        collections_path=collections_path,
        simple=simple,
    )
    if collections_to_update is None:
        return

    before_data = svc.capture_before_state(
        this_module,
        collections=collections_to_update,
        collections_path=collections_path,
        simple=simple,
    )

    # Fat service: attempt every collection, collecting per-collection failures.
    # The command owns the progress/credential seams (kept importable here so
    # the UI-parity source scan still sees create_phased_progress in update.py)
    # and hands them to the loop; reading them here preserves test patching.
    outcome = svc.run_update_loop(
        this_module,
        collections=collections_to_update,
        before_data=before_data,
        update_wiring=update_wiring,
        collections_path=collections_path,
        config_service=config_service,
        simple=simple,
        noop_context=NoOpContext,
        create_phased_progress=create_phased_progress,
        ensure_credentials=ensure_credentials_for_source,
    )

    # Notify user if config was newly created during the updates
    if not config_existed and _config_existed_before(config_service) and not simple:
        console.print()
        print_info(
            f"Created new config file with default settings: "
            f"{_get_config_path(config_service)}"
        )

    # Simple output mode: JSON status
    if simple:
        svc.aggregate_simple_outcome(
            this_module, outcome, before_data, collections_path
        )
        payload: dict[str, Any] = {
            "status": "error" if outcome.failed_collections else "updated",
            "collections": outcome.updated_collections,
            "total_documents": outcome.total_docs,
            "total_chunks": outcome.total_chunks,
        }
        if outcome.failed_collections:
            payload["failed_collections"] = outcome.failed_collections
        print_json(payload)
        if outcome.failed_collections:
            raise typer.Exit(1)
        return

    # Result summary for multiple collections (not shown in verbose mode — logs cover it)
    if len(collections_to_update) > 1 and not is_verbose_mode():
        summary = create_summary(
            "Result",
            svc.build_result_summary_text(len(collections_to_update), outcome),
        )
        console.print(summary)
        console.print()

    # A per-collection failure must still exit non-zero even though every
    # collection was attempted (foundation/6 E8).
    if outcome.failed_collections:
        names = ", ".join(f"'{n}'" for n in outcome.failed_collections)
        print_error(f"Failed to update: {names}")
        raise typer.Exit(1)


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "update_service":
        from indexed.core.v1.engine import update

        return update
    elif name == "SourceConfig":
        from indexed.core.v1.engine import SourceConfig

        return SourceConfig
    elif name == "svc_status":
        from indexed.core.v1.engine import status

        return status
    elif name == "inspect":
        from indexed.core.v1.engine import inspect

        return inspect
    elif name == "setup_root_logger":
        from ...utils.logging import setup_root_logger

        return setup_root_logger
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
