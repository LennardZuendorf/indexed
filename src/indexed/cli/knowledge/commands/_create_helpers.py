"""Shared helper functions for create commands.

This module contains common logic extracted from create_files, create_jira,
and create_confluence commands to eliminate code duplication.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, Callable, Type, TYPE_CHECKING
from loguru import logger
from pydantic import BaseModel

if TYPE_CHECKING:
    from indexed.core.engine import SourceConfig

from indexed.config import ConfigService, StorageMode, ValidationResult

from ...utils.logging import is_verbose_mode, setup_root_logger
from ...utils.console import console
from ...utils.context_managers import NoOpContext
from ...utils.components import print_success, print_error, print_warning
from ...utils.format import format_source_type
from ...utils.progress_bar import create_phased_progress, build_progress_title
from ...utils.credentials import (
    apply_cli_credential_overrides,
    ensure_credentials_for_source,
    is_credential_field,
)


# Sentinel returned by `_snapshot_config_toml` when the snapshot read itself
# fails (e.g. a permission error). Distinct from `None` (file legitimately
# absent) so `_restore_config_toml` never guesses and deletes a file whose
# prior content it could not actually read.
_SNAPSHOT_READ_FAILED = object()


def _snapshot_config_toml(path: Path) -> object:
    """Capture config.toml's exact current bytes so a failed create can restore it.

    Review Finding 1 (foundation/6b): the Jira/Confluence *credential*
    prompts (``ensure_atlassian_cloud_credentials`` / ``ensure_server_credentials``
    / ``prompt_credential_field`` in ``utils/credentials.py``) persist
    email/login straight to config.toml via ``set_value(..., sensitive=False)``
    during Phase 1/1c — before creation is attempted. Snapshotting the raw
    bytes here (before any of that runs) and restoring on failure closes the
    leak for every prompted value at one seam, without touching how/where
    credentials are written on success (email/login must still land in
    config.toml then, so a later ``update`` can re-authenticate).

    Returns:
        ``None`` when the file does not exist yet, the raw bytes when it
        does, or ``_SNAPSHOT_READ_FAILED`` when the read itself raised —
        this function must never raise and block a create run from starting.
    """
    try:
        return path.read_bytes() if path.exists() else None
    except Exception as exc:  # noqa: BLE001 - snapshotting must never block a run
        logger.warning(
            "Could not snapshot config.toml before create ({}); "
            "restore will be skipped for this run if it fails.",
            exc,
        )
        return _SNAPSHOT_READ_FAILED


def _restore_config_toml(path: Path, snapshot: object) -> None:
    """Best-effort restore of config.toml to a prior snapshot after a failed create.

    Deletes the file when the snapshot recorded "did not exist"; otherwise
    writes the captured bytes back atomically (tmp -> fsync -> replace,
    mirroring ``TomlStore.write()``'s own atomic-write pattern). Never
    raises — a restore failure is logged, not propagated, so it can't mask
    the original create failure that triggered it.
    """
    if snapshot is _SNAPSHOT_READ_FAILED:
        return
    try:
        if snapshot is None:
            if path.exists():
                path.unlink()
            return
        if not isinstance(snapshot, (bytes, bytearray)):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".restore.tmp")
        with open(tmp, "wb") as f:
            f.write(snapshot)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception as exc:  # noqa: BLE001 - restore must never mask the real error
        logger.warning("Could not restore config.toml after failed create: {}", exc)


def execute_create_command(
    collection: str,
    source_type: str,
    config_class: Type[BaseModel],
    namespace: str,
    cli_overrides: Dict[str, Any],
    prompt_missing_fields: Callable[[ValidationResult, ConfigService, str], None],
    build_source_config: Callable[[Dict[str, Any], str], "SourceConfig"],
    success_message_suffix: str,
    verbose: bool,
    json_logs: bool,
    log_level: Optional[str],
    use_cache: bool,
    force: bool,
    progress_message: Optional[str] = None,
    verbose_pre_creation_log: Optional[Callable[[Dict[str, Any]], None]] = None,
    pre_creation_display: Optional[Callable[[Dict[str, Any]], None]] = None,
    local: bool = False,
    source_path_key: Optional[str] = None,
) -> None:
    """Common execution flow for all create commands.

    This function encapsulates the shared logic for creating collections:
    1. Setup logging
    2. Initialize ConfigService
    3. Validate requirements
    4. Prompt for missing values
    5. Build SourceConfig
    6. Execute with progress display
    7. Verify and display result

    Args:
        collection: Name of the collection to create
        source_type: Type of source (e.g., 'localFiles', 'jiraCloud', 'confluence')
        config_class: Pydantic config class for validation
        namespace: Config namespace (e.g., 'sources.jira')
        cli_overrides: Dictionary of CLI parameter overrides
        prompt_missing_fields: Callback to prompt for connector-specific missing fields
        build_source_config: Callback to build SourceConfig from validated config
        success_message_suffix: Suffix for success message (e.g., 'from files', 'from Jira')
        verbose: Enable verbose logging
        json_logs: Enable JSON log format
        log_level: Explicit log level
        use_cache: Enable document caching
        force: Force overwrite existing collection
        progress_message: Optional custom progress message (defaults to "Creating {collection}")
        verbose_pre_creation_log: Optional callback to log connector-specific info before creation (in verbose mode)
        local: If True, save the collection to .indexed/data/ in the current directory instead of ~/.indexed/data/
    """
    # Setup logging based on options
    effective_level = log_level or ("INFO" if verbose else None)
    setup_root_logger(level_str=effective_level, json_mode=json_logs)

    import typer

    mode_override: Optional[StorageMode] = None
    engine_flag: Optional[str] = None
    try:
        import click

        ctx = click.get_current_context(silent=True)
        if ctx and ctx.obj:
            mode_override = ctx.obj.get("mode_override")
            engine_flag = ctx.obj.get("engine")
    except Exception:
        pass
    if local:
        mode_override = "local"

    from indexed.cli.composition import (
        resolve_collections_context,
        resolve_engine_selector,
    )

    cli_ctx = resolve_collections_context(mode_override=mode_override)
    config = cli_ctx.config_service
    collections_path = str(cli_ctx.collections_path)
    caches_path = str(cli_ctx.caches_path)
    # Resolve the engine for this NEW collection via the selector chain (R3):
    # --engine flag > INDEXED__CORE__ENGINE > [core] engine > default "1".
    resolved_engine = resolve_engine_selector(engine_flag, config)

    # Review Finding 1 (foundation/6b): snapshot config.toml's exact bytes
    # before ANY prompt/write in this run. The Jira/Confluence credential
    # prompts (Phase 1c below) persist email/login straight to config.toml
    # even though the CLI-override overlay (R3, bug E4) does not — so on
    # ANY failure of this run we restore this snapshot, leaving config.toml
    # byte-identical to before the command ran. On success we leave it as
    # written, so prompted credentials persist for a later `update`.
    config_toml_path = config.store.resolved_config_path()
    config_snapshot = _snapshot_config_toml(config_toml_path)

    run_succeeded = False
    try:
        # Start this create run with a clean in-memory overlay (R3) so a stale
        # override from a prior (possibly failed) create in the same process
        # can never leak into this one (foundation/6b bug E4).
        config.clear_overlay()

        if local or mode_override == "local":
            from indexed.config import ensure_storage_dirs, get_local_root

            ensure_storage_dirs(get_local_root(config.workspace), is_local=True)

        if is_verbose_mode():
            logger.info("Starting %s collection creation...", source_type)
            logger.info("Resolving configuration parameters...")
            logger.info("Using source type: %s", source_type)
            logger.info(
                "Validating configuration requirements for %s...",
                config_class.__name__,
            )

        # Validate requirements using ConfigService

        validation = config.validate_requirements(
            config_class=config_class,
            namespace=namespace,
            cli_overrides=cli_overrides,
        )

        if is_verbose_mode():
            logger.info(
                "Validation result: %d fields present, %d missing",
                len(validation.present),
                len(validation.missing),
            )

        # Phase 1b: Apply CLI credential overrides before prompting so connector
        # prompt logic can see tokens already provided on the command line.
        apply_cli_credential_overrides(source_type, cli_overrides)

        # Phase 1: Prompt for missing values using connector-specific callback
        if validation.missing:
            prompt_missing_fields(validation, config, namespace)

        # Phase 1c: Ensure credentials (interactive prompt + .env persistence)
        ensure_credentials_for_source(source_type, config, namespace=namespace)

        # Make CLI overrides visible to the connector's from_config() read via
        # the in-memory overlay only — never persisted to config.toml (R3; a
        # failed create must not leave the override on disk, foundation/6b
        # bug E4).
        for key, value in cli_overrides.items():
            if is_credential_field(key):
                continue
            config.set_overlay(f"{namespace}.{key}", value)

        # Log resolved configuration in verbose mode
        if is_verbose_mode():
            logger.info("Configuration resolved:")
            for field_name, value in validation.present.items():
                field_meta = validation.field_info.get(field_name, {})
                if field_meta.get("sensitive"):
                    logger.info("  %s: ******** (sensitive)", field_name)
                else:
                    logger.info("  %s: %s", field_name, value)
            logger.info("  Collection: %s", collection)

        # Use module-level lazy-loaded services (supports mocking in tests)
        from . import _create_helpers as this_module

        svc_create = this_module.svc_create
        svc_status = this_module.svc_status

        # Check if collection already exists (prompt unless --force)
        if not force:
            from indexed.core.engine import collection_exists

            if collection_exists(collection, collections_path=collections_path):
                console.print()
                print_warning(f"Collection '{collection}' already exists.")
                if not typer.confirm("Overwrite?", default=False):
                    raise typer.Exit(0)

        # Build source config using connector-specific callback
        cfg = build_source_config(validation.present, collection)

        # Show source summary before spinner (non-verbose only — verbose path uses logger)
        if pre_creation_display and not is_verbose_mode():
            pre_creation_display(validation.present)

        from ...composition import wiring_kwargs_for_create

        create_wiring = wiring_kwargs_for_create(cli_ctx)

        # Phase 2: Create collection with appropriate UI mode
        creation_error = None
        try:
            if is_verbose_mode():
                # Verbose mode: show all logs, no spinner
                with NoOpContext():
                    if verbose_pre_creation_log:
                        verbose_pre_creation_log(validation.present)
                    logger.info("Creating collection '%s'...", collection)
                    svc_create(
                        [cfg],
                        engine=resolved_engine,
                        use_cache=use_cache,
                        force=force,
                        collections_path=collections_path,
                        caches_path=caches_path,
                        **create_wiring,
                    )
            else:
                # Normal mode: phased progress display
                title = build_progress_title(
                    "Creating", collection, format_source_type(source_type)
                )

                with create_phased_progress(title=title) as phased:
                    phased.start_phase("Preparing")
                    try:
                        svc_create(
                            [cfg],
                            engine=resolved_engine,
                            use_cache=use_cache,
                            force=force,
                            phased_progress=phased,
                            collections_path=collections_path,
                            caches_path=caches_path,
                            **create_wiring,
                        )
                    except Exception as e:
                        creation_error = e

        except Exception as e:
            creation_error = e

        # If creation failed, show error and exit
        if creation_error:
            print_error(f"Failed to create collection: {str(creation_error)}")
            if is_verbose_mode():
                logger.exception("Full error details:")
            raise typer.Exit(1)

        # Phase 3: Verify collection was created by checking if manifest exists
        try:
            if is_verbose_mode():
                logger.info("Verifying collection was created...")

            collections = svc_status([collection], collections_path=collections_path)

            # Check if we got a valid collection (not just an error placeholder with 0 docs)
            # A valid collection should have updated_time set
            if collections and len(collections) > 0 and collections[0].updated_time:
                doc_count = collections[0].number_of_documents
                if is_verbose_mode():
                    logger.info(
                        "Collection created successfully with %d documents",
                        doc_count,
                    )

                # Build success message with optional source path
                source_display = ""
                if source_path_key and source_path_key in validation.present:
                    source_display = f" ({validation.present[source_path_key]})"

                console.print()
                print_success(
                    f"Collection '{collection}' created with {doc_count} documents {success_message_suffix}{source_display}"
                )
                console.print()
            else:
                print_error("Collection creation failed - no valid collection found")
                raise typer.Exit(1)

        except typer.Exit:
            # Re-raise typer.Exit to preserve exit code
            raise
        except Exception as e:
            print_error(f"Failed to verify collection: {str(e)}")
            if is_verbose_mode():
                logger.exception("Full error details:")
            raise typer.Exit(1)

        run_succeeded = True

    finally:
        # Review Finding 1: a run that didn't reach the success path above —
        # any exception, or a `typer.Exit` for any reason (creation failure,
        # verify failure, or the user declining an overwrite) — restores
        # config.toml so it never carries a prompted-but-unused credential.
        if not run_succeeded:
            _restore_config_toml(config_toml_path, config_snapshot)
        # Review Finding 2: clear the in-memory overlay at the end of every
        # run (success or failure), not just at the start — the start-of-run
        # clear alone left process-global overlay state dangling after a
        # run finished, a latent footgun for the long-lived MCP server.
        config.clear_overlay()


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "svc_create":
        from indexed.core.engine import create

        return create
    elif name == "svc_status":
        from indexed.core.engine import status

        return status
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
