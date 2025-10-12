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
from .utils.components.theme import get_help_theme_styles, get_accent_style
from .utils.banner import print_indexed_banner

# Override Typer's default Rich help colors with our custom accent color
# This must be done before Typer initializes its help formatting
import typer.rich_utils

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
    level = (
        (log_level or ("INFO" if verbose else None) or env_level).upper()
        if (log_level or verbose or env_level)
        else None
    )
    # Default is WARNING (set in setup_root_logger)
    json_mode = json_logs or os.getenv("INDEXED_LOG_JSON", "false").lower() == "true"
    setup_root_logger(level_str=level, json_mode=json_mode)


# Shared default indexer constant (kept here for backward compatibility with tests)
DEFAULT_INDEXER = "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"


# Register new commands using plugin architecture
from . import knowledge  # noqa: E402
from . import config  # noqa: E402
from . import mcp  # noqa: E402

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
    help="Create New Collections (Files, Jira, Confluence)",
    rich_help_panel="Knowledge / Index Management",
)
app.command(
    "index search",
    rich_help_panel="Knowledge / Index Management",
    help="Search Indexed Collections",
)(knowledge.search.search)
app.command(
    "index inspect",
    rich_help_panel="Knowledge / Index Management",
    help="Inspect Indexed Collections",
)(knowledge.inspect.inspect_collections)
app.command(
    "index update",
    rich_help_panel="Knowledge / Index Management",
    help="Update Indexed Collections",
)(knowledge.update.update)
app.command(
    "index remove",
    rich_help_panel="Knowledge / Index Management",
    help="Remove Indexed Collections",
)(knowledge.remove.remove)

# Configuration Management - Hide The Group, Show Only Subcommands
app.add_typer(
    config.app,
    name="config",
    help="Manage Indexed Configuration",
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
    "config init",
    rich_help_panel="Configuration Management",
    help="Initialize Configuration File",
)(config.init)
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
    "config reset",
    rich_help_panel="Configuration Management",
    help="Reset Configuration To Defaults",
)(config.reset)

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
