"""Create command for adding collections (hardcoded subcommands)."""

from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.v1.engine.services import SourceConfig

import typer
from loguru import logger

# Import ConfigService at module level so tests can patch
from indexed_config import ConfigService

# Import utilities for progress and logging
from ...utils.logging import is_verbose_mode
from ...utils.console import console
from ...utils.components.theme import (
    get_heading_style,
    get_accent_style,
)
from ...utils.components import print_error
from ...utils.credentials import (
    prompt_credential_field,
    is_credential_field,
    check_server_auth_present,
)
from ._create_helpers import execute_create_command


def _is_cloud(url: str) -> bool:
    """
    Determine whether a given Atlassian base URL refers to the cloud-hosted service.

    Returns:
        True if the URL ends with ".atlassian.net", False otherwise.
    """
    return url.endswith(".atlassian.net")


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
    local: bool = typer.Option(
        False,
        "--local",
        help="Save the collection to .indexed/ in the current directory instead of ~/.indexed/",
        rich_help_panel="Storage",
    ),
):
    """Create a Files collection with comprehensive parameter resolution and progress tracking."""
    # Use module-level lazy-loaded services (supports mocking in tests)
    from . import create as this_module

    local_files_config_class = this_module.LocalFilesConfig

    # Files connector (no cloud/server split)
    source_type = "localFiles"
    config_class = local_files_config_class
    namespace = "sources.files"

    # Build CLI overrides (map CLI params to schema fields)
    cli_overrides: Dict[str, Any] = {}
    if path:
        cli_overrides["path"] = path
    if include:
        cli_overrides["include_patterns"] = include
    if exclude:
        cli_overrides["exclude_patterns"] = exclude
    if fail_fast:
        cli_overrides["fail_fast"] = fail_fast

    def prompt_missing_files_fields(
        validation: Dict[str, Any], config: ConfigService, ns: str
    ) -> None:
        """Prompt for missing Files-specific fields."""
        if not validation.missing:
            return

        if not is_verbose_mode():
            console.print()
            console.print(
                f"[{get_heading_style()}]Files Configuration[/{get_heading_style()}]"
            )
            console.print()

        for field_name in validation.missing:
            field_info = validation.field_info[field_name]

            if is_verbose_mode():
                logger.info("Prompting for missing field: %s", field_name)

            # Prompt based on field name
            if field_name == "path":
                value = console.input(
                    f"[{get_accent_style()}]Path to files or directory[/{get_accent_style()}]: "
                )
            elif field_name == "include_patterns":
                patterns_input = console.input(
                    f"[{get_accent_style()}]Include patterns (comma-separated)[/{get_accent_style()}] [*]: "
                )
                value = (
                    [p.strip() for p in patterns_input.split(",")]
                    if patterns_input
                    else ["*"]
                )
            elif field_name == "exclude_patterns":
                patterns_input = console.input(
                    f"[{get_accent_style()}]Exclude patterns (comma-separated)[/{get_accent_style()}] []: "
                )
                value = (
                    [p.strip() for p in patterns_input.split(",")]
                    if patterns_input
                    else []
                )
            elif field_name == "fail_fast":
                fail_fast_input = console.input(
                    f"[{get_accent_style()}]Stop on first error? (yes/no)[/{get_accent_style()}] [no]: "
                )
                value = fail_fast_input.lower() in ["yes", "y", "true"]
            else:
                # Generic fallback
                value = console.input(
                    f"[{get_accent_style()}]{field_name}[/{get_accent_style()}]: "
                )

            # Save using ConfigService
            config.set_value(f"{ns}.{field_name}", value, field_info=field_info)
            validation.present[field_name] = value

            if is_verbose_mode():
                logger.info(
                    "Saved %s to %s",
                    field_name,
                    "env" if field_info.get("sensitive") else "config",
                )

    def build_files_source_config(
        present: Dict[str, Any], coll_name: str
    ) -> "SourceConfig":
        """Build SourceConfig for Files connector."""
        # Use module-level lazy-loaded services (supports mocking in tests)
        from . import create as this_module

        return this_module.SourceConfig(
            name=coll_name,
            type=source_type,
            base_url_or_path=present["path"],
            indexer=this_module.DEFAULT_INDEXER,
            reader_opts={
                "includePatterns": present.get("include_patterns", ["*"]),
                "excludePatterns": present.get("exclude_patterns", []),
                "failFast": present.get("fail_fast", False),
            },
        )

    # Use shared helper
    execute_create_command(
        collection=collection,
        source_type=source_type,
        config_class=config_class,
        namespace=namespace,
        cli_overrides=cli_overrides,
        prompt_missing_fields=prompt_missing_files_fields,
        build_source_config=build_files_source_config,
        success_message_suffix="from files",
        verbose=verbose,
        json_logs=json_logs,
        log_level=log_level,
        use_cache=use_cache,
        force=force,
        local=local,
    )


@app.command(
    "jira", help="Create a new collection from Jira issues using a base JQL query."
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
    local: bool = typer.Option(
        False,
        "--local",
        help="Save the collection to .indexed/ in the current directory instead of ~/.indexed/",
        rich_help_panel="Storage",
    ),
):
    """Create a Jira collection with comprehensive parameter resolution and progress tracking."""
    # Use module-level lazy-loaded services (supports mocking in tests)
    from . import create as this_module

    jira_cloud_config_class = this_module.JiraCloudConfig
    jira_config_class = this_module.JiraConfig

    # Use a single namespace for Jira config - detect Cloud vs Server from URL at runtime
    namespace = "sources.jira"

    # Phase 0: Determine the URL first (needed to detect cloud vs server)
    config = ConfigService.instance()
    resolved_url = url or config.get(f"{namespace}.url")

    # If URL is still unknown, prompt for it first before determining source type
    url_was_prompted = False
    if not resolved_url:
        if not is_verbose_mode():
            console.print()
            console.print(
                f"[{get_heading_style()}]Jira Configuration[/{get_heading_style()}]"
            )
            console.print()

        if is_verbose_mode():
            logger.info("URL not known, prompting user...")

        resolved_url = console.input(
            f"[{get_accent_style()}]Jira URL[/{get_accent_style()}]: "
        )
        url_was_prompted = True

        if not resolved_url:
            print_error("Jira URL is required")
            raise typer.Exit(1)

    # Determine connector type based on the URL (Cloud = *.atlassian.net)
    if _is_cloud(resolved_url):
        source_type = "jiraCloud"
        config_class = jira_cloud_config_class
    else:
        source_type = "jira"
        config_class = jira_config_class

    # Build CLI overrides (url is now always known)
    cli_overrides = {"url": resolved_url}
    if jql:
        cli_overrides["query"] = jql
    if email:
        cli_overrides["email"] = email
    if token:
        cli_overrides["api_token"] = token

    def prompt_missing_jira_fields(
        validation: Dict[str, Any], config: ConfigService, ns: str
    ) -> None:
        """Prompt for missing Jira-specific fields."""
        # URL already handled above, exclude it from missing fields
        missing_fields = [f for f in validation.missing if f != "url"]
        if not missing_fields:
            return

        # Show header if not already shown (URL was from CLI/config)
        if not url_was_prompted and not is_verbose_mode():
            console.print()
            console.print(
                f"[{get_heading_style()}]Jira Configuration[/{get_heading_style()}]"
            )
            console.print()

        for field_name in missing_fields:
            field_info = validation.field_info[field_name]

            if is_verbose_mode():
                logger.info("Prompting for missing field: %s", field_name)

            # Use shared credential prompting for credential fields
            if is_credential_field(field_name):
                value = prompt_credential_field(
                    field_name, field_info, config, ns, source_type
                )
            # Handle non-credential fields
            elif field_name in ["query", "jql"]:
                value = (
                    console.input(
                        f"[{get_accent_style()}]JQL query[/{get_accent_style()}] [project = PROJ]: "
                    )
                    or "project = PROJ"
                )
                config.set_value(f"{ns}.{field_name}", value, field_info=field_info)
            else:
                # Generic fallback
                value = console.input(
                    f"[{get_accent_style()}]{field_name}[/{get_accent_style()}]: "
                )
                config.set_value(f"{ns}.{field_name}", value, field_info=field_info)

            validation.present[field_name] = value

            if is_verbose_mode():
                logger.info(
                    "Saved %s to %s",
                    field_name,
                    "env" if field_info.get("sensitive") else "config",
                )

    def build_jira_source_config(
        present: Dict[str, Any], coll_name: str
    ) -> "SourceConfig":
        """Build SourceConfig for Jira connector."""
        # Use module-level lazy-loaded services (supports mocking in tests)
        from . import create as this_module

        return this_module.SourceConfig(
            name=coll_name,
            type=source_type,
            base_url_or_path=present["url"],
            query=present["query"],
            indexer=this_module.DEFAULT_INDEXER,
            reader_opts={},  # Credentials are read from ConfigService by connector
        )

    def verbose_jira_log(present: Dict[str, Any]) -> None:
        """Log Jira-specific info before creation in verbose mode."""
        logger.info("Connecting to Jira at %s...", present["url"])
        logger.info("Using JQL query: %s", present["query"])

    # Use shared helper
    execute_create_command(
        collection=collection,
        source_type=source_type,
        config_class=config_class,
        namespace=namespace,
        cli_overrides=cli_overrides,
        prompt_missing_fields=prompt_missing_jira_fields,
        build_source_config=build_jira_source_config,
        success_message_suffix="from Jira",
        verbose=verbose,
        json_logs=json_logs,
        log_level=log_level,
        use_cache=use_cache,
        force=force,
        progress_message=f"Connecting to {resolved_url}",
        verbose_pre_creation_log=verbose_jira_log,
        local=local,
    )


@app.command(
    "confluence",
    help="Create a new collection from Confluence pages using a base CQL query.",
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
    local: bool = typer.Option(
        False,
        "--local",
        help="Save the collection to .indexed/ in the current directory instead of ~/.indexed/",
        rich_help_panel="Storage",
    ),
):
    """
    Create a Confluence collection by resolving configuration, executing the ingestion, and verifying the result.

    Resolves required settings (Confluence URL, CQL/query, credentials, and read-options) from CLI options, config, or interactive prompts; detects cloud vs server deployment from the URL; applies CLI overrides; then creates the collection (uses a verbose log path or a spinner/progress UI) with support for on-disk caching and an optional force-delete of existing collections. After creation, verifies the collection exists and reports the resulting document count; on failure prints an error and exits with a non-zero status.
    """
    # Use module-level lazy-loaded services (supports mocking in tests)
    from . import create as this_module

    confluence_cloud_config_class = this_module.ConfluenceCloudConfig
    confluence_config_class = this_module.ConfluenceConfig

    # Use a single namespace for Confluence config - detect Cloud vs Server from URL at runtime
    namespace = "sources.confluence"

    # Phase 0: Determine the URL first (needed to detect cloud vs server)
    config = ConfigService.instance()
    resolved_url = url or config.get(f"{namespace}.url")

    # If URL is still unknown, prompt for it first before determining source type
    url_was_prompted = False
    if not resolved_url:
        if not is_verbose_mode():
            console.print()
            console.print(
                f"[{get_heading_style()}]Confluence Configuration[/{get_heading_style()}]"
            )
            console.print()

        if is_verbose_mode():
            logger.info("URL not known, prompting user...")

        resolved_url = console.input(
            f"[{get_accent_style()}]Confluence URL[/{get_accent_style()}]: "
        )
        url_was_prompted = True

        if not resolved_url:
            print_error("Confluence URL is required")
            raise typer.Exit(1)

    # Determine connector type based on the URL (Cloud = *.atlassian.net)
    if _is_cloud(resolved_url):
        source_type = "confluenceCloud"
        config_class = confluence_cloud_config_class
    else:
        source_type = "confluence"
        config_class = confluence_config_class

    # Build CLI overrides (url is now always known)
    cli_overrides = {"url": resolved_url}
    if cql:
        cli_overrides["query"] = cql
    if email:
        cli_overrides["email"] = email
    if token:
        cli_overrides["api_token"] = token
    # Always include read_all_comments (has a default of True)
    cli_overrides["read_all_comments"] = read_all_comments

    def prompt_missing_confluence_fields(
        validation: Dict[str, Any], config: ConfigService, ns: str
    ) -> None:
        """Prompt for missing Confluence-specific fields."""
        # URL already handled above, exclude it from missing fields
        missing_fields = [f for f in validation.missing if f != "url"]

        # For Confluence Server/DC: auth fields (token, login, password) are optional in schema
        # but at least one auth method is required by the connector.
        # Check if we need to prompt for auth credentials using shared function.
        if source_type == "confluence":
            if not check_server_auth_present(
                validation.present,
                token_env_var="CONF_TOKEN",
                login_env_var="CONF_LOGIN",
                password_env_var="CONF_PASSWORD",
            ):
                # No auth found, prompt for token
                if "token" not in missing_fields:
                    missing_fields.append("token")
                if is_verbose_mode():
                    logger.info("No auth credentials found, will prompt for token")

        if not missing_fields:
            return

        # Show header if not already shown (URL was from CLI/config)
        if not url_was_prompted and not is_verbose_mode():
            console.print()
            console.print(
                f"[{get_heading_style()}]Confluence Configuration[/{get_heading_style()}]"
            )
            console.print()

        for field_name in missing_fields:
            field_info = validation.field_info[field_name]

            if is_verbose_mode():
                logger.info("Prompting for missing field: %s", field_name)

            # Use shared credential prompting for credential fields
            if is_credential_field(field_name):
                value = prompt_credential_field(
                    field_name, field_info, config, ns, source_type
                )
            # Handle non-credential fields
            elif field_name in ["query", "cql"]:
                value = (
                    console.input(
                        f"[{get_accent_style()}]CQL query[/{get_accent_style()}] [type=page]: "
                    )
                    or "type=page"
                )
                config.set_value(f"{ns}.{field_name}", value, field_info=field_info)
            else:
                # Generic fallback
                value = console.input(
                    f"[{get_accent_style()}]{field_name}[/{get_accent_style()}]: "
                )
                config.set_value(f"{ns}.{field_name}", value, field_info=field_info)

            validation.present[field_name] = value

            if is_verbose_mode():
                logger.info(
                    "Saved %s to %s",
                    field_name,
                    "env" if field_info.get("sensitive") else "config",
                )

    def build_confluence_source_config(
        present: Dict[str, Any], coll_name: str
    ) -> "SourceConfig":
        """Build SourceConfig for Confluence connector."""
        # Use module-level lazy-loaded services (supports mocking in tests)
        from . import create as this_module

        return this_module.SourceConfig(
            name=coll_name,
            type=source_type,
            base_url_or_path=present["url"],
            query=present["query"],
            indexer=this_module.DEFAULT_INDEXER,
            reader_opts={"readAllComments": present.get("read_all_comments", True)},
        )

    def verbose_confluence_log(present: Dict[str, Any]) -> None:
        """Log Confluence-specific info before creation in verbose mode."""
        logger.info("Connecting to Confluence at %s...", present["url"])
        logger.info("Using CQL query: %s", present["query"])

    # Use shared helper
    execute_create_command(
        collection=collection,
        source_type=source_type,
        config_class=config_class,
        namespace=namespace,
        cli_overrides=cli_overrides,
        prompt_missing_fields=prompt_missing_confluence_fields,
        build_source_config=build_confluence_source_config,
        success_message_suffix="from Confluence",
        verbose=verbose,
        json_logs=json_logs,
        log_level=log_level,
        use_cache=use_cache,
        force=force,
        progress_message=f"Connecting to {resolved_url}",
        verbose_pre_creation_log=verbose_confluence_log,
        local=local,
    )


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "DEFAULT_INDEXER":
        from core.v1.constants import DEFAULT_INDEXER

        return DEFAULT_INDEXER
    elif name == "SourceConfig":
        from core.v1.engine.services import SourceConfig

        return SourceConfig
    elif name == "LocalFilesConfig":
        from connectors.files import LocalFilesConfig

        return LocalFilesConfig
    elif name == "JiraCloudConfig":
        from connectors.jira import JiraCloudConfig

        return JiraCloudConfig
    elif name == "JiraConfig":
        from connectors.jira import JiraConfig

        return JiraConfig
    elif name == "ConfluenceCloudConfig":
        from connectors.confluence import ConfluenceCloudConfig

        return ConfluenceCloudConfig
    elif name == "ConfluenceConfig":
        from connectors.confluence import ConfluenceConfig

        return ConfluenceConfig
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
