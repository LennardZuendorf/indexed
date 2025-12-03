"""Indexed CLI application.

Provides stateless commands backed by services.
"""

# Suppress SWIG deprecation warnings from faiss (upstream issue, not fixed yet)
# Must be done before any faiss imports occur
import warnings

warnings.filterwarnings("ignore", message="builtin type Swig.*")

import os  # noqa: E402
import sys  # noqa: E402
import typer  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Optional, TYPE_CHECKING  # noqa: E402
from rich.console import Console  # noqa: E402

if TYPE_CHECKING:
    from indexed_config import ConfigService
from rich.theme import Theme  # noqa: E402
from .utils.logging import setup_root_logger  # noqa: E402
from .utils.components.theme import get_help_theme_styles, get_accent_style  # noqa: E402
from .utils.components import print_success  # noqa: E402
from .utils.banner import print_indexed_banner  # noqa: E402
from .utils.storage_info import (  # noqa: E402
    print_storage_info,
    get_storage_mode_and_reason,
    StorageMode,
)

# Override Typer's default Rich help colors with our custom accent color
# This must be done before Typer initializes its help formatting
import typer.rich_utils  # noqa: E402

typer.rich_utils.STYLE_OPTION = f"bold {get_accent_style()}"
typer.rich_utils.STYLE_SWITCH = f"bold {get_accent_style()}"
typer.rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = f"bold {get_accent_style()}"
typer.rich_utils.STYLE_COMMANDS_TABLE_COLUMN_WIDTH_RATIO = (None, None)

# Re-export service interfaces for tests and command modules to reference dynamically
from core.v1.engine.services import (  # noqa: E402
    SourceConfig,
    clear as svc_clear,
    create as svc_create,
    search as svc_search,
    status as svc_status,
    update as svc_update,
)

# Note: These service functions now accept config_service parameter for new config system

# Configure Rich console with custom theme for help display
_help_console = Console(theme=Theme(get_help_theme_styles()))

# Main Typer application
app = typer.Typer(
    add_completion=True,
    help="Index Institutional Knowledge and Make it Available for AI Agents and LLMs!",
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    context_settings={
        "help_option_names": ["--help"],
    },
    rich_help_panel=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# Early Flag Parsing for Global Storage Options
# ─────────────────────────────────────────────────────────────────────────────
# These flags need to be parsed early because they affect ConfigService
# initialization which must happen before any command runs.

def _parse_early_storage_flags() -> tuple[bool, bool]:
    """Parse --local and --global flags from sys.argv.
    
    These flags are "global" in the sense that they can appear anywhere
    in the command line and affect all commands. We parse them early
    and remove them from sys.argv so they don't cause "unknown option" errors.
    
    Returns:
        Tuple of (use_local, use_global)
    """
    use_local = False
    use_global = False
    
    # Check for flags and remove them from argv
    new_argv = [sys.argv[0]]
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--local":
            use_local = True
        elif arg == "--global":
            use_global = True
        else:
            new_argv.append(arg)
        i += 1
    
    # Update sys.argv with flags removed
    sys.argv[:] = new_argv
    
    return use_local, use_global


# Parse storage flags early (before Typer processes args)
_EARLY_USE_LOCAL, _EARLY_USE_GLOBAL = False, False


# Console for conflict prompts
_prompt_console = Console()


# Global logging init via callback (runs before subcommands)
@app.callback(invoke_without_command=True)
def _init_app(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose (INFO) logging with rich formatting",
        rich_help_panel="Logging",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Set explicit logging level (DEBUG, INFO, WARNING, ERROR). Overrides --verbose.",
        case_sensitive=False,
        show_choices=True,
        rich_help_panel="Logging",
    ),
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Output logs as JSON (structured)",
        rich_help_panel="Logging",
    ),
) -> None:
    """Initialize the indexed CLI application.
    
    Global flags available on ALL commands:
      --local   Use local storage (./.indexed) instead of global
      --global  Force global storage (~/.indexed), ignoring local config
    """
    global _EARLY_USE_LOCAL, _EARLY_USE_GLOBAL
    
    # Show banner before help if main command help is requested
    # This only triggers when no subcommand is invoked
    if ctx.invoked_subcommand is None and not ctx.resilient_parsing:
        # Check if help was requested
        if "--help" in sys.argv or "-h" in sys.argv:
            print_indexed_banner()

    # Resolve effective level with precedence: CLI > env > default
    # --verbose sets INFO level for seeing operation progress
    # --log-level=DEBUG can be used for deep debugging
    env_level = os.getenv("INDEXED_LOG_LEVEL")
    level = (
        (log_level or ("INFO" if verbose else None) or env_level).upper()
        if (log_level or verbose or env_level)
        else None
    )
    # Default is WARNING (set in setup_root_logger)
    json_mode = json_logs or os.getenv("INDEXED_LOG_JSON", "false").lower() == "true"
    setup_root_logger(level_str=level, json_mode=json_mode)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Storage Mode Resolution (using early-parsed flags)
    # ─────────────────────────────────────────────────────────────────────────
    
    # Import here to avoid circular imports
    from indexed_config import (
        ConfigService,
        has_local_config,
        get_local_root,
        ensure_storage_dirs,
    )
    
    # Use the early-parsed flags
    use_local = _EARLY_USE_LOCAL
    use_global = _EARLY_USE_GLOBAL
    
    # Validate mutually exclusive flags
    if use_local and use_global:
        _prompt_console.print(
            "[red]Error:[/red] Cannot use both --local and --global flags together."
        )
        raise typer.Exit(1)
    
    workspace = Path.cwd()
    local_exists = has_local_config(workspace)
    
    # If --local flag used but no local .indexed exists, create it
    if use_local and not local_exists:
        local_root = get_local_root(workspace)
        ensure_storage_dirs(local_root)
        # Create empty config.toml
        config_path = local_root / "config.toml"
        config_path.write_text(
            "# Indexed Local Configuration\n"
            "# This file was auto-created when using --local flag\n\n"
            "[storage]\n"
            'mode = "local"  # Always use local storage for this project\n'
        )
        print_success(f"Created local .indexed folder at {local_root}")
        local_exists = True
    
    # Determine mode override from flags or local existence
    mode_override: Optional[StorageMode] = None
    if use_local:
        mode_override = "local"
    elif use_global:
        mode_override = "global"
    elif local_exists:
        # If local .indexed exists, prefer it by default
        mode_override = "local"
    
    # Initialize ConfigService with resolved mode
    config_service = ConfigService.instance(
        workspace=workspace,
        mode_override=mode_override,
        reset=True,  # Reset to ensure fresh state with new settings
    )
    
    # Check for storage.mode setting in config
    config_mode = config_service.get("storage.mode")
    if config_mode in ("local", "global") and not use_local and not use_global:
        # Config setting takes precedence over auto-detection
        mode_override = config_mode
        # Re-initialize with config-specified mode
        config_service = ConfigService.instance(
            workspace=workspace,
            mode_override=mode_override,
            reset=True,
        )
    
    # Handle storage mode display and context setup (only if running a command)
    if ctx.invoked_subcommand is not None and not ctx.resilient_parsing:
        _resolve_and_display_storage_mode(
            ctx=ctx,
            config_service=config_service,
            mode_override=mode_override,
            workspace=workspace,
            local_exists=local_exists,
            use_local_flag=use_local,
            use_global_flag=use_global,
            config_mode=config_mode,
        )


def _resolve_and_display_storage_mode(
    ctx: typer.Context,
    config_service: "ConfigService",  # type: ignore[name-defined]
    mode_override: Optional[StorageMode],
    workspace: Path,
    local_exists: bool,
    use_local_flag: bool,
    use_global_flag: bool,
    config_mode: Optional[str],
) -> None:
    """Resolve storage mode, display indicator, and set up context.
    
    Args:
        ctx: Typer context to store resolved mode.
        config_service: ConfigService instance.
        mode_override: Resolved mode override.
        workspace: Current workspace path.
        local_exists: Whether local .indexed exists.
        use_local_flag: Whether --local flag was used.
        use_global_flag: Whether --global flag was used.
        config_mode: storage.mode value from config.
    """
    from indexed_config import get_local_root, get_global_root
    
    # Determine the reason for using this mode
    mode, reason = get_storage_mode_and_reason(
        has_local=local_exists,
        mode_override="local" if use_local_flag else ("global" if use_global_flag else None),
        config_mode=config_mode if config_mode in ("local", "global") else None,
        workspace_pref=config_service.get_workspace_preference(workspace),
    )
    
    # Get the actual path being used
    if mode == "local":
        storage_path = get_local_root(workspace)
    else:
        storage_path = get_global_root()
    
    # Always display storage mode indicator
    print_storage_info(
        console=_prompt_console,
        mode=mode,
        path=storage_path,
        reason=reason,
        newline_before=False,
        newline_after=True,
    )
    
    # Store in context for commands to access
    ctx.ensure_object(dict)
    ctx.obj["storage_mode"] = mode
    ctx.obj["storage_path"] = storage_path
    ctx.obj["config_service"] = config_service


# Re-export default indexer constant for backward compatibility with tests
from core.v1.constants import DEFAULT_INDEXER  # noqa: E402


# Register new commands using plugin architecture
from . import knowledge  # noqa: E402
from . import config  # noqa: E402
from . import mcp  # noqa: E402
from . import info  # noqa: E402

# Knowledge / Index Management - Register hidden group and flat commands
app.add_typer(
    knowledge.app,
    name="knowledge",
    help="Knowledge & Index Management Commands",
    rich_help_panel="Knowledge / Index Management",
    hidden=True,
)

app.add_typer(
    knowledge.app,
    name="index",
    help="Knowledge & Index Management Commands",
    rich_help_panel="Knowledge / Index Management",
    hidden=True,
)

# Show Individual Knowledge Commands In Main Help (Flat Structure)
app.add_typer(
    knowledge.create.app,
    name="index create",
    help="Create New Collections using Connectors",
    rich_help_panel="Knowledge / Index Management",
)
app.command(
    "index search",
    rich_help_panel="Knowledge / Index Management",
    help="Search one or all Collections",
)(knowledge.search.search)
app.command(
    "index inspect",
    rich_help_panel="Knowledge / Index Management",
    help="Inspect Collections",
)(knowledge.inspect.inspect_collections)
app.command(
    "index update",
    rich_help_panel="Knowledge / Index Management",
    help="Update a Collection",
)(knowledge.update.update)
app.command(
    "index remove",
    rich_help_panel="Knowledge / Index Management",
    help="Remove one or more Collections",
)(knowledge.remove.remove)

# Configuration Management - Hide The Group, Show Only Subcommands
app.add_typer(
    config.app,
    name="config",
    help="Manage Configuration",
    rich_help_panel="Config Management",
    hidden=True,
)
# Show Individual Config Commands In Main Help
app.command(
    "config inspect",
    rich_help_panel="Configuration Management",
    help="Inspect Configuration Settings",
)(config.inspect)
app.command(
    "config update",
    rich_help_panel="Configuration Management",
    help="Update Configuration Settings Interactively",
)(config.update)
app.command(
    "config set",
    rich_help_panel="Configuration Management",
    help="Set Configuration Values",
)(config.set_config)
app.command(
    "config validate",
    rich_help_panel="Configuration Management",
    help="Validate Configuration",
)(config.validate)
app.command(
    "config delete",
    rich_help_panel="Configuration Management",
    help="Delete Configuration Keys",
)(config.delete_config)

# MCP Server - Hide The Group, Show Only Subcommands
app.add_typer(
    mcp.app,
    name="mcp",
    help="Start MCP Server For AI Integration",
    rich_help_panel="MCP Server",
    hidden=True,
)
# Show Individual MCP Commands In Main Help
app.command(
    "mcp run", rich_help_panel="MCP Server", help="Run The MCP Server With FastMCP CLI"
)(mcp.run)
app.command(
    "mcp dev",
    rich_help_panel="MCP Server",
    help="Run MCP Server In Development Mode With Inspector",
)(mcp.dev)
app.command(
    "mcp inspect", rich_help_panel="MCP Server", help="Inspect MCP Server Capabilities"
)(mcp.inspect)
app.command(
    "mcp fastmcp",
    rich_help_panel="MCP Server",
    help="Direct Passthrough To FastMCP CLI",
)(mcp.fastmcp)

# Resources - Hide The Group, Show Only Subcommands
app.add_typer(
    info.app,
    name="info",
    help="Resources Commands",
    rich_help_panel="Resources",
    hidden=True,
)
# Show Individual Info Commands In Main Help
app.command(
    "docs",
    rich_help_panel="Resources",
    help="Open Documentation in Browser",
)(info.docs)
app.command(
    "license",
    rich_help_panel="Resources",
    help="Display License and Terms",
)(info.license_terms)


# ─────────────────────────────────────────────────────────────────────────────
# Migration Command
# ─────────────────────────────────────────────────────────────────────────────

@app.command(
    "migrate",
    rich_help_panel="Configuration Management",
    help="Migrate legacy ./data/ to global ~/.indexed/data/",
)
def migrate_data(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be migrated without copying",
    ),
) -> None:
    """Migrate legacy data from ./data/ to the global storage location.
    
    This command helps transition from the old local storage structure
    (./data/collections) to the new global storage (~/.indexed/data/collections).
    
    The original data is preserved - you can delete ./data/ manually after
    verifying the migration was successful.
    """
    from indexed_config import get_global_root
    from .utils.migration import migrate_legacy_data, has_legacy_data
    
    console = Console()
    
    if not has_legacy_data():
        console.print("[dim]No legacy data found at ./data/[/dim]")
        console.print()
        console.print("[dim]Nothing to migrate.[/dim]")
        return
    
    target_root = get_global_root()
    migrate_legacy_data(target_root, console, dry_run=dry_run)


__all__ = [
    "app",
    "main",
    "DEFAULT_INDEXER",
    # Re-exports used by tests for monkeypatching
    "svc_create",
    "svc_update",
    "svc_clear",
    "svc_search",
    "svc_status",
    "SourceConfig",
]


def main() -> None:
    """Main entry point that displays banner before help."""
    global _EARLY_USE_LOCAL, _EARLY_USE_GLOBAL
    
    # Parse storage flags early (before Typer processes args)
    # This allows --local and --global to work with any subcommand
    _EARLY_USE_LOCAL, _EARLY_USE_GLOBAL = _parse_early_storage_flags()
    
    # Show banner if --help is the only argument (main help, not subcommand help)
    if len(sys.argv) == 2 and sys.argv[1] in ["--help", "-h"]:
        print_indexed_banner()
    app()


if __name__ == "__main__":
    main()
