"""Indexed CLI application.

Provides legacy proxies and stateless commands backed by services.
"""

import os
import sys
import typer
from typing import Optional
from rich.console import Console
from rich.theme import Theme
from utils.logger import setup_root_logger
from cli.components import get_help_theme_styles, ACCENT_COLOR
from cli.utils.banner import print_indexed_banner

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

# Register legacy command group
from .commands.legacy.legacy import legacy_app  # noqa: E402

app.add_typer(legacy_app, name="legacy")

# Register new commands using plugin architecture
from .commands import create, search, update, delete, config, mcp  # noqa: E402
from .commands.inspect import inspect_collections  # noqa: E402

app.add_typer(create.app, name="create")
app.add_typer(config.app, name="config")
app.add_typer(mcp.app, name="mcp")
app.command("search")(search.search)
app.command("update")(update.update)
app.command("delete")(delete.delete)
app.command("inspect")(inspect_collections)



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
