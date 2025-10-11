"""Indexed CLI application.

Provides stateless commands backed by services.
"""

import os
import sys
import typer
from typing import Optional
from rich.console import Console
from rich.theme import Theme
from .utils.logging import setup_root_logger
from .components.theme import get_help_theme_styles, ACCENT_COLOR
from .utils.banner import print_indexed_banner

# Override Typer's default Rich help colors with our custom accent color
# This must be done before Typer initializes its help formatting
import typer.rich_utils
typer.rich_utils.STYLE_OPTION = f"bold {ACCENT_COLOR}"
typer.rich_utils.STYLE_SWITCH = f"bold {ACCENT_COLOR}"
typer.rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = f"bold {ACCENT_COLOR}"
typer.rich_utils.STYLE_COMMANDS_TABLE_COLUMN_WIDTH_RATIO = (None, None)

# Re-export service interfaces for tests and command modules to reference dynamically
from core.v1.engine.services import (
    SourceConfig,
    clear as svc_clear,
    create as svc_create,
    search as svc_search,
    status as svc_status,
    update as svc_update,
)

# Configure Rich console with custom theme for help display
_help_console = Console(theme=Theme(get_help_theme_styles()))

# Main Typer application
app = typer.Typer(
    add_completion=True,
    help="Index Institutional Knowledge and Make it Available for AI Agents and LLMs!",
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    context_settings={"help_option_names": ["--help"]},
    rich_help_panel=True,
)
# Global logging init via callback (runs before subcommands)
@app.callback(invoke_without_command=True)
def _init_logging(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False, "--verbose", help="Enable verbose (INFO) logging with rich formatting"
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
        False, "--json-logs", help="Output logs as JSON (structured)"
    ),
) -> None:
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
    level = (log_level or ("INFO" if verbose else None) or env_level).upper() if (log_level or verbose or env_level) else None
    # Default is WARNING (set in setup_root_logger)
    json_mode = json_logs or os.getenv("INDEXED_LOG_JSON", "false").lower() == "true"
    setup_root_logger(level_str=level, json_mode=json_mode)

# Shared default indexer constant (kept here for backward compatibility with tests)
DEFAULT_INDEXER = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"


# Register new commands using plugin architecture
from .commands.knowledge import create, search, update, remove, inspect  # noqa: E402
from .commands import config  # noqa: E402
from . import mcp  # noqa: E402

# Knowledge / Index Management commands (flat with help panel)
app.add_typer(create.app, name="create", help="Create new collections (files, jira, confluence)", rich_help_panel="Knowledge / Index Management")
app.command("search", rich_help_panel="Knowledge / Index Management")(search.search)
app.command("inspect", rich_help_panel="Knowledge / Index Management")(inspect.inspect_collections)
app.command("update", rich_help_panel="Knowledge / Index Management")(update.update)
app.command("remove", rich_help_panel="Knowledge / Index Management")(remove.remove)

# Configuration Management - Both nested and flattened approaches
app.add_typer(config.app, name="config", help="Manage configuration (inspect, set, validate, reset)", rich_help_panel="Configuration Management", hidden=True)

# Also register flattened commands for direct access
app.command("config inspect", rich_help_panel="Configuration Management")(config.inspect)
app.command("config init", rich_help_panel="Configuration Management")(config.init)
app.command("config set", rich_help_panel="Configuration Management")(config.set_config)
app.command("config validate", rich_help_panel="Configuration Management")(config.validate)
app.command("config reset", rich_help_panel="Configuration Management")(config.reset)

# MCP Server (nested with help panel)
from . import mcp_cli

# Also register flattened MCP commands for direct access
app.command("mcp run", rich_help_panel="MCP Server")(mcp_cli.run)
app.command("mcp dev", rich_help_panel="MCP Server")(mcp_cli.dev)
app.command("mcp inspect", rich_help_panel="MCP Server")(mcp_cli.inspect)
app.command("mcp fastmcp", rich_help_panel="MCP Server")(mcp_cli.fastmcp)

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
    # Show banner if --help is the only argument (main help, not subcommand help)
    if len(sys.argv) == 2 and sys.argv[1] in ["--help", "-h"]:
        print_indexed_banner()
    app()


if __name__ == "__main__":
    main()
