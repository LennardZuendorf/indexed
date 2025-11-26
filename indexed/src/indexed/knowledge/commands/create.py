"""Create command for adding collections (hardcoded subcommands)."""

from typing import List
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from io import StringIO
import logging as stdlib_logging

import typer
from loguru import logger

# Import constants
from core.v1.constants import DEFAULT_INDEXER

# Import utilities for progress and logging
from ...utils.logging import is_verbose_mode
from ...utils.progress_bar import create_operation_progress
from ...utils.console import console
from ...utils.components.theme import (
    get_heading_style,
    get_accent_style,
    get_default_style,
)


def _is_cloud(url: str) -> bool:
    return url.endswith(".atlassian.net")


class _NoOpContext:
    """No-op context manager for verbose mode (no spinner)."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@contextmanager
def suppress_core_output():
    """Context manager to suppress all core logging and output."""
    # Capture all output streams
    stdout_capture = StringIO()
    stderr_capture = StringIO()

    # Save original logging level (stdlib logging used by core)
    original_level = stdlib_logging.getLogger().level

    try:
        # Suppress all logging output
        stdlib_logging.getLogger().setLevel(stdlib_logging.CRITICAL)

        # Redirect stdout and stderr
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            yield

    finally:
        # Restore original logging level
        stdlib_logging.getLogger().setLevel(original_level)


app = typer.Typer(help="Create new collections")


@app.command("files", help="Create a new collection from local files or folders.")
def create_files(
    collection: str = typer.Option(
        "files",
        "--collection",
        "-c",
        help="Name of the collection (default: files).",
    ),
    path: str = typer.Option(
        None,
        "--path",
        "-p",
        help="Path to the root directory or file(s) (from config or prompt if not provided).",
    ),
    include: List[str] = typer.Option(
        None,
        "--include",
        help="List of regex patterns for files/directories to include (can be specified multiple times).",
        show_default=False,
    ),
    exclude: List[str] = typer.Option(
        None,
        "--exclude",
        help="List of regex patterns for files/directories to exclude (can be specified multiple times).",
        show_default=False,
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast/--no-fail-fast",
        help="Stop and abort if the first file read error occurs.",
    ),
    use_cache: bool = typer.Option(
        True,
        "--use-cache/--no-cache",
        help="Enable on-disk cache for faster reindexing of unchanged content.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete any existing collection with the same name before creating a new one.",
    ),
):
    """Create a Files collection with comprehensive parameter resolution and progress tracking."""
    from indexed_config import ConfigService
    from core.v1.engine.services import SourceConfig, create as svc_create, status
    from connectors.files import LocalFilesConfig

    # Initialize ConfigService (auto-loads .env)
    config = ConfigService()
    
    if is_verbose_mode():
        logger.info("Starting Files collection creation...")
        logger.info("Resolving configuration parameters...")
    
    # Files connector (no cloud/server split)
    source_type = "localFiles"
    config_class = LocalFilesConfig
    namespace = "sources.local_files"
    
    if is_verbose_mode():
        logger.info("Using source type: %s", source_type)
    
    # Build CLI overrides (map CLI params to schema fields)
    cli_overrides = {}
    if path:
        cli_overrides["path"] = path
    if include:
        cli_overrides["include_patterns"] = include
    if exclude:
        cli_overrides["exclude_patterns"] = exclude
    if fail_fast is not None:
        cli_overrides["fail_fast"] = fail_fast
    
    # Validate requirements using ConfigService (generic!)
    if is_verbose_mode():
        logger.info("Validating configuration requirements for %s...", config_class.__name__)
    
    validation = config.validate_requirements(
        config_class=config_class,
        namespace=namespace,
        cli_overrides=cli_overrides
    )
    
    if is_verbose_mode():
        logger.info("Validation result: %d fields present, %d missing", 
                    len(validation["present"]), len(validation["missing"]))
    
    # Phase 1: Prompt for missing values
    if validation["missing"]:
        if not is_verbose_mode():
            console.print()
            console.print(f"[{get_heading_style()}]Files Configuration[/{get_heading_style()}]")
            console.print()
        
        for field_name in validation["missing"]:
            field_info = validation["field_info"][field_name]
            
            if is_verbose_mode():
                logger.info("Prompting for missing field: %s", field_name)
            
            # Prompt based on field name
            if field_name == "path":
                value = console.input(f"[{get_accent_style()}]Path to files or directory[/{get_accent_style()}]: ")
            elif field_name == "include_patterns":
                patterns_input = console.input(f"[{get_accent_style()}]Include patterns (comma-separated)[/{get_accent_style()}] [.*]: ")
                value = [p.strip() for p in patterns_input.split(",")] if patterns_input else [".*"]
            elif field_name == "exclude_patterns":
                patterns_input = console.input(f"[{get_accent_style()}]Exclude patterns (comma-separated)[/{get_accent_style()}] []: ")
                value = [p.strip() for p in patterns_input.split(",")] if patterns_input else []
            elif field_name == "fail_fast":
                fail_fast_input = console.input(f"[{get_accent_style()}]Stop on first error? (yes/no)[/{get_accent_style()}] [no]: ")
                value = fail_fast_input.lower() in ["yes", "y", "true"]
            else:
                # Generic fallback
                value = console.input(f"[{get_accent_style()}]{field_name}[/{get_accent_style()}]: ")
            
            # Save using ConfigService (it decides .env vs .toml based on field_info)
            config.set_value(
                f"{namespace}.{field_name}",
                value,
                field_info=field_info
            )
            validation["present"][field_name] = value
            
            if is_verbose_mode():
                logger.info("Saved %s to %s", field_name, "env" if field_info.get("sensitive") else "config")
    
    # Also set CLI overrides in config for connector to read
    for key, value in cli_overrides.items():
        field_info = validation["field_info"].get(key)
        config.set_value(f"{namespace}.{key}", value, field_info=field_info)
    
    # Log resolved configuration in verbose mode
    if is_verbose_mode():
        logger.info("Configuration resolved:")
        for field_name, value in validation["present"].items():
            if validation["field_info"][field_name].get("sensitive"):
                logger.info("  %s: ******** (sensitive)", field_name)
            else:
                logger.info("  %s: %s", field_name, value)
        logger.info("  Collection: %s", collection)
    
    # Build source config
    cfg = SourceConfig(
        name=collection,
        type=source_type,
        base_url_or_path=validation["present"]["path"],
        indexer=DEFAULT_INDEXER,
        reader_opts={
            "includePatterns": validation["present"].get("include_patterns", [".*"]),
            "excludePatterns": validation["present"].get("exclude_patterns", []),
            "failFast": validation["present"].get("fail_fast", False),
        },
    )
    
    # Phase 2: Create collection with appropriate UI mode
    try:
        if is_verbose_mode():
            # Verbose mode: show all logs, no spinner
            with _NoOpContext():
                logger.info("Reading files from %s...", validation["present"]["path"])
                logger.info("Include patterns: %s", validation["present"].get("include_patterns", [".*"]))
                logger.info("Exclude patterns: %s", validation["present"].get("exclude_patterns", []))
                logger.info("Creating collection '%s'...", collection)
                svc_create([cfg], config_service=config, use_cache=use_cache, force=force)
        else:
            # Normal mode: show header and spinner with clean output
            console.print()
            console.print(
                f"[{get_heading_style()}]Creating Files collection: "
                f"[{get_accent_style()}]{collection}[/{get_accent_style()}]"
                f"[/{get_heading_style()}]"
            )
            
            operation_desc = f"[{get_default_style()}]Reading files from {validation['present']['path']}[/{get_default_style()}]"
            with create_operation_progress(operation_desc) as (progress, task_id, callback):
                with suppress_core_output():
                    svc_create([cfg], config_service=config, use_cache=use_cache, force=force, progress_callback=callback)
        
        # Phase 3: Verify collection was created
        if is_verbose_mode():
            logger.info("Verifying collection was created...")
        
        collections = status([collection])
        
        if collections and len(collections) > 0:
            doc_count = collections[0].number_of_documents
            if is_verbose_mode():
                logger.info("Collection created successfully with %d documents", doc_count)
            
            console.print()
            typer.echo(f"✓ Collection '{collection}' created with {doc_count} documents from files")
        else:
            console.print()
            typer.secho("⚠ No files found matching patterns - collection not created", fg="yellow")
            raise typer.Exit(1)
    
    except typer.Exit:
        # Re-raise typer.Exit to preserve exit code
        raise
    except Exception as e:
        console.print()
        typer.secho(f"✗ Failed to create collection: {str(e)}", fg="red", err=True)
        if is_verbose_mode():
            logger.exception("Full error details:")
        raise typer.Exit(1)


@app.command(
    "jira",
    help="Create a new collection from Jira issues using a base JQL query."
)
def create_jira(
    collection: str = typer.Option(
        "jira",
        "--collection",
        "-c",
        help="Name of the collection (default: jira).",
    ),
    url: str = typer.Option(
        None,
        "--url",
        "-u",
        help="Base URL of the Jira instance (from config or prompt if not provided).",
    ),
    jql: str = typer.Option(
        None,
        "--jql",
        "--query",
        "-q",
        help="JQL query (from config or prompt if not provided).",
    ),
    email: str = typer.Option(
        None,
        "--email",
        help="Atlassian account email (overrides config/env).",
    ),
    token: str = typer.Option(
        None,
        "--token",
        help="Atlassian API token (overrides env ATLASSIAN_TOKEN).",
    ),
    use_cache: bool = typer.Option(
        True,
        "--use-cache/--no-cache",
        help="Enable on-disk cache for faster reindexing of unchanged issues.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete any existing collection with the same name before creating a new one.",
    ),
):
    """Create a Jira collection with comprehensive parameter resolution and progress tracking."""
    from indexed_config import ConfigService
    from core.v1.engine.services import SourceConfig, create as svc_create, status
    from connectors.jira import JiraCloudConfig, JiraConfig

    # Initialize ConfigService (auto-loads .env)
    config = ConfigService()
    
    if is_verbose_mode():
        logger.info("Starting Jira collection creation...")
        logger.info("Resolving configuration parameters...")
    
    # Determine connector type from URL (if provided) or check config
    temp_url = url or config.get("sources.jira_cloud.url") or config.get("sources.jira.url")
    if temp_url and _is_cloud(temp_url):
        source_type = "jiraCloud"
        config_class = JiraCloudConfig
        namespace = "sources.jira_cloud"
    else:
        source_type = "jira"
        config_class = JiraConfig
        namespace = "sources.jira"
    
    if is_verbose_mode():
        logger.info("Detected source type: %s", source_type)
    
    # Build CLI overrides
    cli_overrides = {}
    if url:
        cli_overrides["url"] = url
    if jql:
        cli_overrides["query"] = jql
    if email:
        cli_overrides["email"] = email
    if token:
        cli_overrides["api_token"] = token
    
    # Validate requirements using ConfigService (generic!)
    if is_verbose_mode():
        logger.info("Validating configuration requirements for %s...", config_class.__name__)
    
    validation = config.validate_requirements(
        config_class=config_class,
        namespace=namespace,
        cli_overrides=cli_overrides
    )
    
    if is_verbose_mode():
        logger.info("Validation result: %d fields present, %d missing", 
                    len(validation["present"]), len(validation["missing"]))
    
    # Phase 1: Prompt for missing values
    if validation["missing"]:
        if not is_verbose_mode():
            console.print()
            console.print(f"[{get_heading_style()}]Jira Configuration[/{get_heading_style()}]")
            console.print()
        
        for field_name in validation["missing"]:
            field_info = validation["field_info"][field_name]
            
            if is_verbose_mode():
                logger.info("Prompting for missing field: %s", field_name)
            
            # Prompt based on field name
            if field_name == "url":
                value = console.input(f"[{get_accent_style()}]Jira URL[/{get_accent_style()}]: ")
            elif field_name in ["query", "jql"]:
                value = console.input(f"[{get_accent_style()}]JQL query[/{get_accent_style()}] [project = PROJ]: ") or "project = PROJ"
            elif field_name == "email":
                value = console.input(f"[{get_accent_style()}]Email[/{get_accent_style()}]: ")
            elif field_name in ["api_token", "token"]:
                from rich.prompt import Prompt
                value = Prompt.ask(f"[{get_accent_style()}]API token[/{get_accent_style()}]", password=True)
            elif field_name == "login":
                value = console.input(f"[{get_accent_style()}]Username[/{get_accent_style()}]: ")
            elif field_name == "password":
                from rich.prompt import Prompt
                value = Prompt.ask(f"[{get_accent_style()}]Password[/{get_accent_style()}]", password=True)
            else:
                # Generic fallback
                value = console.input(f"[{get_accent_style()}]{field_name}[/{get_accent_style()}]: ")
            
            # Save using ConfigService (it decides .env vs .toml based on field_info)
            config.set_value(
                f"{namespace}.{field_name}",
                value,
                field_info=field_info
            )
            validation["present"][field_name] = value
            
            if is_verbose_mode():
                logger.info("Saved %s to %s", field_name, "env" if field_info.get("sensitive") else "config")
    
    # Also set CLI overrides in config for connector to read
    for key, value in cli_overrides.items():
        field_info = validation["field_info"].get(key)
        config.set_value(f"{namespace}.{key}", value, field_info=field_info)
    
    # Log resolved configuration in verbose mode
    if is_verbose_mode():
        logger.info("Configuration resolved:")
        for field_name, value in validation["present"].items():
            if validation["field_info"][field_name].get("sensitive"):
                logger.info("  %s: ******** (sensitive)", field_name)
            else:
                logger.info("  %s: %s", field_name, value)
        logger.info("  Collection: %s", collection)
    
    # Build source config
    cfg = SourceConfig(
        name=collection,
        type=source_type,
        base_url_or_path=validation["present"]["url"],
        query=validation["present"]["query"],
        indexer=DEFAULT_INDEXER,
        reader_opts={},  # Credentials are read from ConfigService by connector
    )
    
    # Phase 2: Create collection with appropriate UI mode
    try:
        if is_verbose_mode():
            # Verbose mode: show all logs, no spinner
            with _NoOpContext():
                logger.info("Connecting to Jira at %s...", validation["present"]["url"])
                logger.info("Using JQL query: %s", validation["present"]["query"])
                logger.info("Creating collection '%s'...", collection)
                svc_create([cfg], config_service=config, use_cache=use_cache, force=force)
        else:
            # Normal mode: show header and spinner with clean output
            console.print()
            console.print(
                f"[{get_heading_style()}]Creating Jira collection: "
                f"[{get_accent_style()}]{collection}[/{get_accent_style()}]"
                f"[/{get_heading_style()}]"
            )
            
            operation_desc = f"[{get_default_style()}]Connecting to {validation['present']['url']}[/{get_default_style()}]"
            with create_operation_progress(operation_desc) as (progress, task_id, callback):
                with suppress_core_output():
                    svc_create([cfg], config_service=config, use_cache=use_cache, force=force, progress_callback=callback)
        
        # Phase 3: Verify collection was created
        if is_verbose_mode():
            logger.info("Verifying collection was created...")
        
        collections = status([collection])
        
        if collections and len(collections) > 0:
            doc_count = collections[0].number_of_documents
            if is_verbose_mode():
                logger.info("Collection created successfully with %d documents", doc_count)
            
            console.print()
            typer.echo(f"✓ Collection '{collection}' created with {doc_count} documents from Jira")
        else:
            console.print()
            typer.secho("⚠ No documents found matching JQL query - collection not created", fg="yellow")
            raise typer.Exit(1)
    
    except typer.Exit:
        # Re-raise typer.Exit to preserve exit code
        raise
    except Exception as e:
        console.print()
        typer.secho(f"✗ Failed to create collection: {str(e)}", fg="red", err=True)
        if is_verbose_mode():
            logger.exception("Full error details:")
        raise typer.Exit(1)


@app.command(
    "confluence",
    help="Create a new collection from Confluence pages using a base CQL query."
)
def create_confluence(
    collection: str = typer.Option(
        "confluence",
        "--collection",
        "-c",
        help="Name of the collection (default: confluence).",
    ),
    url: str = typer.Option(
        None,
        "--url",
        "-u",
        help="Base URL of the Confluence instance (from config or prompt if not provided).",
    ),
    cql: str = typer.Option(
        None,
        "--cql",
        "--query",
        "-q",
        help="CQL query (from config or prompt if not provided).",
    ),
    email: str = typer.Option(
        None,
        "--email",
        help="Atlassian account email (overrides config/env).",
    ),
    token: str = typer.Option(
        None,
        "--token",
        help="Atlassian API token (overrides env ATLASSIAN_TOKEN).",
    ),
    read_all_comments: bool = typer.Option(
        True,
        "--read-all-comments/--first-level-comments",
        help="Read all nested comments if enabled, otherwise include only first-level comments.",
    ),
    use_cache: bool = typer.Option(
        True,
        "--use-cache/--no-cache",
        help="Enable on-disk cache for faster reindexing of unchanged pages.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Delete any existing collection with the same name before creating a new one.",
    ),
):
    """Create a Confluence collection with comprehensive parameter resolution and progress tracking."""
    from indexed_config import ConfigService
    from core.v1.engine.services import SourceConfig, create as svc_create, status
    from connectors.confluence import ConfluenceCloudConfig, ConfluenceConfig

    # Initialize ConfigService (auto-loads .env)
    config = ConfigService()
    
    if is_verbose_mode():
        logger.info("Starting Confluence collection creation...")
        logger.info("Resolving configuration parameters...")
    
    # Determine connector type from URL (if provided) or check config
    temp_url = url or config.get("sources.confluence_cloud.url") or config.get("sources.confluence.url")
    if temp_url and _is_cloud(temp_url):
        source_type = "confluenceCloud"
        config_class = ConfluenceCloudConfig
        namespace = "sources.confluence_cloud"
    else:
        source_type = "confluence"
        config_class = ConfluenceConfig
        namespace = "sources.confluence"
    
    if is_verbose_mode():
        logger.info("Detected source type: %s", source_type)
    
    # Build CLI overrides
    cli_overrides = {}
    if url:
        cli_overrides["url"] = url
    if cql:
        cli_overrides["query"] = cql
    if email:
        cli_overrides["email"] = email
    if token:
        cli_overrides["api_token"] = token
    if read_all_comments is not None:
        cli_overrides["read_all_comments"] = read_all_comments
    
    # Validate requirements using ConfigService (generic!)
    if is_verbose_mode():
        logger.info("Validating configuration requirements for %s...", config_class.__name__)
    
    validation = config.validate_requirements(
        config_class=config_class,
        namespace=namespace,
        cli_overrides=cli_overrides
    )
    
    if is_verbose_mode():
        logger.info("Validation result: %d fields present, %d missing", 
                    len(validation["present"]), len(validation["missing"]))
    
    # Phase 1: Prompt for missing values
    if validation["missing"]:
        if not is_verbose_mode():
            console.print()
            console.print(f"[{get_heading_style()}]Confluence Configuration[/{get_heading_style()}]")
            console.print()
        
        for field_name in validation["missing"]:
            field_info = validation["field_info"][field_name]
            
            if is_verbose_mode():
                logger.info("Prompting for missing field: %s", field_name)
            
            # Prompt based on field name
            if field_name == "url":
                value = console.input(f"[{get_accent_style()}]Confluence URL[/{get_accent_style()}]: ")
            elif field_name in ["query", "cql"]:
                value = console.input(f"[{get_accent_style()}]CQL query[/{get_accent_style()}] [type=page]: ") or "type=page"
            elif field_name == "email":
                value = console.input(f"[{get_accent_style()}]Email[/{get_accent_style()}]: ")
            elif field_name in ["api_token", "token"]:
                from rich.prompt import Prompt
                value = Prompt.ask(f"[{get_accent_style()}]API token[/{get_accent_style()}]", password=True)
            elif field_name == "login":
                value = console.input(f"[{get_accent_style()}]Username[/{get_accent_style()}]: ")
            elif field_name == "password":
                from rich.prompt import Prompt
                value = Prompt.ask(f"[{get_accent_style()}]Password[/{get_accent_style()}]", password=True)
            else:
                # Generic fallback
                value = console.input(f"[{get_accent_style()}]{field_name}[/{get_accent_style()}]: ")
            
            # Save using ConfigService (it decides .env vs .toml based on field_info)
            config.set_value(
                f"{namespace}.{field_name}",
                value,
                field_info=field_info
            )
            validation["present"][field_name] = value
            
            if is_verbose_mode():
                logger.info("Saved %s to %s", field_name, "env" if field_info.get("sensitive") else "config")
    
    # Also set CLI overrides in config for connector to read
    for key, value in cli_overrides.items():
        field_info = validation["field_info"].get(key)
        config.set_value(f"{namespace}.{key}", value, field_info=field_info)
    
    # Log resolved configuration in verbose mode
    if is_verbose_mode():
        logger.info("Configuration resolved:")
        for field_name, value in validation["present"].items():
            if validation["field_info"][field_name].get("sensitive"):
                logger.info("  %s: ******** (sensitive)", field_name)
            else:
                logger.info("  %s: %s", field_name, value)
        logger.info("  Collection: %s", collection)
    
    # Build source config
    cfg = SourceConfig(
        name=collection,
        type=source_type,
        base_url_or_path=validation["present"]["url"],
        query=validation["present"]["query"],
        indexer=DEFAULT_INDEXER,
        reader_opts={"readAllComments": validation["present"].get("read_all_comments", True)},
    )
    
    # Phase 2: Create collection with appropriate UI mode
    try:
        if is_verbose_mode():
            # Verbose mode: show all logs, no spinner
            with _NoOpContext():
                logger.info("Connecting to Confluence at %s...", validation["present"]["url"])
                logger.info("Using CQL query: %s", validation["present"]["query"])
                logger.info("Creating collection '%s'...", collection)
                svc_create([cfg], config_service=config, use_cache=use_cache, force=force)
        else:
            # Normal mode: show header and spinner with clean output
            console.print()
            console.print(
                f"[{get_heading_style()}]Creating Confluence collection: "
                f"[{get_accent_style()}]{collection}[/{get_accent_style()}]"
                f"[/{get_heading_style()}]"
            )
            
            operation_desc = f"[{get_default_style()}]Connecting to {validation['present']['url']}[/{get_default_style()}]"
            with create_operation_progress(operation_desc) as (progress, task_id, callback):
                with suppress_core_output():
                    svc_create([cfg], config_service=config, use_cache=use_cache, force=force, progress_callback=callback)
        
        # Phase 3: Verify collection was created
        if is_verbose_mode():
            logger.info("Verifying collection was created...")
        
        collections = status([collection])
        
        if collections and len(collections) > 0:
            doc_count = collections[0].number_of_documents
            if is_verbose_mode():
                logger.info("Collection created successfully with %d documents", doc_count)
            
            console.print()
            typer.echo(f"✓ Collection '{collection}' created with {doc_count} documents from Confluence")
        else:
            console.print()
            typer.secho("⚠ No documents found matching CQL query - collection not created", fg="yellow")
            raise typer.Exit(1)
    
    except typer.Exit:
        # Re-raise typer.Exit to preserve exit code
        raise
    except Exception as e:
        console.print()
        typer.secho(f"✗ Failed to create collection: {str(e)}", fg="red", err=True)
        if is_verbose_mode():
            logger.exception("Full error details:")
        raise typer.Exit(1)
