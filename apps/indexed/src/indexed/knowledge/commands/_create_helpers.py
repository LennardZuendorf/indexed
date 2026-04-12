"""Shared helper functions for create commands.

This module contains common logic extracted from create_files, create_jira,
and create_confluence commands to eliminate code duplication.
"""

from typing import Optional, Dict, Any, Callable, Type, TYPE_CHECKING
import typer
from loguru import logger

if TYPE_CHECKING:
    from core.v1.engine.services import SourceConfig

from indexed_config import ConfigService

from ...utils.logging import is_verbose_mode, setup_root_logger
from ...utils.console import console
from ...utils.context_managers import NoOpContext
from ...utils.components import print_success, print_error, print_warning
from ...utils.format import format_source_type
from ...utils.progress_bar import create_phased_progress, build_progress_title


def _build_v2_connector(cfg: "SourceConfig", config_service: Any) -> Any:
    """Build a v2 connector object from a resolved SourceConfig.

    For file connectors, instantiate directly from SourceConfig fields.
    For remote connectors (Jira/Confluence), credentials are already in
    config_service from CLI prompts — use from_config().
    """
    if cfg.type == "localFiles":
        from connectors.files.connector import FileSystemConnector

        return FileSystemConnector(
            path=cfg.base_url_or_path,
            include_patterns=cfg.reader_opts.get("includePatterns", ["*"]),
            exclude_patterns=cfg.reader_opts.get("excludePatterns", []),
            fail_fast=cfg.reader_opts.get("failFast", False),
        )

    from connectors.registry import get_connector_class

    ConnectorClass = get_connector_class(cfg.type)
    return ConnectorClass.from_config(config_service)


def execute_create_command(
    collection: str,
    source_type: str,
    config_class: Type,
    namespace: str,
    cli_overrides: Dict[str, Any],
    prompt_missing_fields: Callable[[Dict[str, Any], ConfigService, str], None],
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
    engine: str = "v1",
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

    # Get ConfigService singleton (auto-loads .env)
    mode_override = "local" if local else None
    config = ConfigService.instance(mode_override=mode_override)

    # Resolve storage paths based on --local flag
    local_collections_path: Optional[str] = None
    local_caches_path: Optional[str] = None
    if local:
        from pathlib import Path
        from indexed_config import ensure_storage_dirs, get_local_root

        workspace = Path.cwd()
        local_root = get_local_root(workspace)
        ensure_storage_dirs(local_root, is_local=True)
        local_collections_path = str(local_root / "data" / "collections")
        local_caches_path = str(local_root / "data" / "caches")

    # Display storage mode indicator (not in verbose mode, to keep logs clean)
    if not is_verbose_mode():
        from ...utils.storage_info import display_storage_mode_for_command

        display_storage_mode_for_command(console)

    if is_verbose_mode():
        logger.info("Starting %s collection creation...", source_type)
        logger.info("Resolving configuration parameters...")
        logger.info("Using source type: %s", source_type)
        logger.info(
            "Validating configuration requirements for %s...", config_class.__name__
        )

    # Validate requirements using ConfigService

    validation = config.validate_requirements(
        config_class=config_class, namespace=namespace, cli_overrides=cli_overrides
    )

    if is_verbose_mode():
        logger.info(
            "Validation result: %d fields present, %d missing",
            len(validation.present),
            len(validation.missing),
        )

    # Phase 1: Prompt for missing values using connector-specific callback
    if validation.missing:
        prompt_missing_fields(validation, config, namespace)

    # Also set CLI overrides in config for connector to read
    for key, value in cli_overrides.items():
        field_info = validation.field_info.get(key)
        config.set_value(f"{namespace}.{key}", value, field_info=field_info)

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
    from pathlib import Path

    svc_create = this_module.svc_create
    svc_status = this_module.svc_status

    # v2 collections directory (None → use default global path)
    v2_collections_dir = (
        Path(local_collections_path) if local_collections_path else None
    )

    # Check if collection already exists (prompt unless --force)
    if not force:
        if engine == "v2":
            from core.v2.services import status as v2_status_check

            existing = v2_status_check([collection], collections_dir=v2_collections_dir)
            collection_exists = bool(existing)
        else:
            from core.v1.engine.services.collection_service import _collection_exists

            collection_exists = _collection_exists(
                collection, collections_path=local_collections_path
            )

        if collection_exists:
            console.print()
            print_warning(f"Collection '{collection}' already exists.")
            if not typer.confirm("Overwrite?", default=False):
                raise typer.Exit(0)

    # Build source config using connector-specific callback
    cfg = build_source_config(validation.present, collection)

    # Show source summary before spinner (non-verbose only — verbose path uses logger)
    if pre_creation_display and not is_verbose_mode():
        pre_creation_display(validation.present)

    # Phase 2: Create collection with appropriate UI mode
    creation_error = None
    try:
        if engine == "v2":
            from core.v2.services import create as v2_create
            from core.v2.config import (
                CoreV2EmbeddingConfig,
                CoreV2StorageConfig,
                register_config as _register_v2_config,
            )

            _register_v2_config(config)  # idempotent — ensure specs are registered
            _provider = config.bind()
            _v2_embed_cfg = _provider.get(CoreV2EmbeddingConfig)
            _v2_store_cfg = _provider.get(CoreV2StorageConfig)
            connector = _build_v2_connector(cfg, config)

            if is_verbose_mode():
                with NoOpContext():
                    if verbose_pre_creation_log:
                        verbose_pre_creation_log(validation.present)
                    logger.info("Creating collection '%s' (v2 engine)...", collection)
                    v2_create(
                        collection,
                        connector,
                        embed_model_name=_v2_embed_cfg.model_name,
                        store_type=_v2_store_cfg.vector_store,
                        collections_dir=v2_collections_dir,
                    )
            else:
                title = build_progress_title(
                    "Creating", collection, format_source_type(source_type)
                )
                with create_phased_progress(title=title) as phased:
                    phased.start_phase("Preparing")
                    try:
                        v2_create(
                            collection,
                            connector,
                            embed_model_name=_v2_embed_cfg.model_name,
                            store_type=_v2_store_cfg.vector_store,
                            collections_dir=v2_collections_dir,
                            progress=phased,
                        )
                    except Exception as e:
                        creation_error = e
        else:
            if is_verbose_mode():
                # Verbose mode: show all logs, no spinner
                with NoOpContext():
                    if verbose_pre_creation_log:
                        verbose_pre_creation_log(validation.present)
                    logger.info("Creating collection '%s'...", collection)
                    svc_create(
                        [cfg],
                        config_service=config,
                        use_cache=use_cache,
                        force=force,
                        collections_path=local_collections_path,
                        caches_path=local_caches_path,
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
                            config_service=config,
                            use_cache=use_cache,
                            force=force,
                            phased_progress=phased,
                            collections_path=local_collections_path,
                            caches_path=local_caches_path,
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

        if engine == "v2":
            from core.v2.services import status as v2_status_verify

            collections = v2_status_verify(
                [collection], collections_dir=v2_collections_dir
            )
        else:
            collections = svc_status(
                [collection], collections_path=local_collections_path
            )

        # Check if we got a valid collection (not just an error placeholder with 0 docs)
        # A valid collection should have updated_time set
        if collections and len(collections) > 0 and collections[0].updated_time:
            doc_count = collections[0].number_of_documents
            if is_verbose_mode():
                logger.info(
                    "Collection created successfully with %d documents", doc_count
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


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "svc_create":
        from core.v1.engine.services import create

        return create
    elif name == "svc_status":
        from core.v1.engine.services import status

        return status
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
