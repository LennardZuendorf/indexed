"""Indexed CLI application - stateless commands backed by services."""

# Process-wide env vars — must be set before any third-party imports.
# Fix OpenMP threading on macOS; suppress noisy third-party output.
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TQDM_DISABLE", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("ORT_LOGGING_LEVEL", "3")

import warnings

warnings.filterwarnings("ignore", message="builtin type Swig.*")
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Optional  # noqa: E402

import typer  # noqa: E402
import typer.rich_utils  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.theme import Theme  # noqa: E402

from utils import bootstrap_logging  # noqa: E402

from .utils.banner import print_indexed_banner  # noqa: E402
from .utils.components import print_info  # noqa: E402
from .utils.components.theme import (  # noqa: E402
    get_accent_style,
    get_dim_style,
    get_error_style,
    get_help_theme_styles,
    get_info_style,
    get_success_style,
    get_warning_style,
)
from .utils.console import console as _shared_console  # noqa: E402

# Single source of truth for level → Rich style mapping. New themes change
# theme.py; logging picks them up automatically.
THEME_STYLES: dict[str, str] = {
    "TRACE": get_dim_style(),
    "DEBUG": get_dim_style(),
    "INFO": get_info_style(),
    "SUCCESS": get_success_style(),
    "WARNING": get_warning_style(),
    "ERROR": get_error_style(),
    "CRITICAL": get_error_style(),
}

typer.rich_utils.STYLE_OPTION = f"bold {get_accent_style()}"
typer.rich_utils.STYLE_SWITCH = f"bold {get_accent_style()}"
typer.rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = f"bold {get_accent_style()}"
typer.rich_utils.STYLE_COMMANDS_TABLE_COLUMN_WIDTH_RATIO = (None, None)

_help_console = Console(theme=Theme(get_help_theme_styles()))

app = typer.Typer(
    add_completion=True,
    help="Index Institutional Knowledge and Make it Available for AI Agents and LLMs!",
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    context_settings={"help_option_names": ["--help"]},
    rich_help_panel=True,
)


@app.callback(invoke_without_command=True)
def _init_app(
    ctx: typer.Context,
    local: bool = typer.Option(
        False,
        "--local",
        help="Use local .indexed/ storage instead of global ~/.indexed/",
        rich_help_panel="Usage Options",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose (INFO) logging",
        rich_help_panel="Debug Options",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Set logging level (DEBUG, INFO, WARNING, ERROR)",
        case_sensitive=False,
        show_choices=True,
        rich_help_panel="Debug Options",
    ),
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Output logs as JSON",
        rich_help_panel="Debug Options",
    ),
    simple_output: bool = typer.Option(
        False,
        "--simple-output",
        help="Machine-readable JSON output (for programmatic use)",
        rich_help_panel="Usage Options",
    ),
) -> None:
    """Initialize logging and handle storage flags. ConfigService is deferred to commands."""
    if simple_output:
        from .utils.simple_output import set_simple_output

        set_simple_output(True)

    if (
        ctx.invoked_subcommand is None
        and not ctx.resilient_parsing
        and ("--help" in sys.argv or "-h" in sys.argv)
    ):
        print_indexed_banner()

    from .utils.simple_output import is_simple_output

    env_level = os.getenv("INDEXED_LOG_LEVEL")
    level = (
        (log_level or ("INFO" if verbose else None) or env_level).upper()
        if (log_level or verbose or env_level)
        else None
    )
    json_mode = (
        json_logs
        or is_simple_output()
        or os.getenv("INDEXED_LOG_JSON", "false").lower() == "true"
    )
    effective_level = (level or "WARNING").upper()
    bootstrap_logging(
        level=effective_level,
        debug=(effective_level == "DEBUG"),
        quiet=(effective_level == "ERROR"),
        rich_console=_shared_console,
        theme_styles=THEME_STYLES,
        log_dir=Path.home() / ".indexed" / "logs",
        json_mode=json_mode,
    )

    # Store resolved mode_override on ctx.obj for subcommands to access
    ctx.ensure_object(dict)
    ctx.obj["mode_override"] = "local" if local else None

    if local:
        from indexed_config import ensure_storage_dirs, get_local_root

        workspace = Path.cwd()
        local_root = get_local_root(workspace)
        ensure_storage_dirs(local_root, is_local=True)


from . import config, info, knowledge, mcp  # noqa: E402
from .debug import debug as debug_command  # noqa: E402
from .init import init as init_command  # noqa: E402

KNOWLEDGE_PANEL = "Knowledge / Index Management"
CONFIG_PANEL = "Configuration Management"
MCP_PANEL = "MCP Server"
RESOURCES_PANEL = "Resources"

app.command(
    "init",
    rich_help_panel="Setup",
    help="Initialize Indexed: download models and create directories",
)(init_command)

app.add_typer(
    knowledge.app,
    name="knowledge",
    help="Knowledge & Index Management Commands",
    rich_help_panel=KNOWLEDGE_PANEL,
    hidden=True,
)
app.add_typer(
    knowledge.app,
    name="index",
    help="Knowledge & Index Management Commands",
    rich_help_panel=KNOWLEDGE_PANEL,
    hidden=True,
)
app.add_typer(
    knowledge.create.app,
    name="index create",
    help="Create New Collections using Connectors",
    rich_help_panel=KNOWLEDGE_PANEL,
)
app.command(
    "index search",
    rich_help_panel=KNOWLEDGE_PANEL,
    help="Search one or all Collections",
)(knowledge.search.search)
app.command(
    "index inspect", rich_help_panel=KNOWLEDGE_PANEL, help="Inspect Collections"
)(knowledge.inspect.inspect_collections)
app.command(
    "index update", rich_help_panel=KNOWLEDGE_PANEL, help="Update a Collection"
)(knowledge.update.update)
app.command(
    "index remove",
    rich_help_panel=KNOWLEDGE_PANEL,
    help="Remove one or more Collections",
)(knowledge.remove.remove)

# Short aliases (hidden — not shown in help)
app.add_typer(knowledge.create.app, name="create", hidden=True)
app.command("search", hidden=True)(knowledge.search.search)
app.command("inspect", hidden=True)(knowledge.inspect.inspect_collections)
app.command("update", hidden=True)(knowledge.update.update)
app.command("remove", hidden=True)(knowledge.remove.remove)

app.add_typer(
    config.app,
    name="config",
    help="Manage Configuration",
    rich_help_panel="Config Management",
    hidden=True,
)
app.command(
    "config inspect",
    rich_help_panel=CONFIG_PANEL,
    help="Inspect Configuration Settings",
)(config.inspect)
app.command(
    "config update",
    rich_help_panel=CONFIG_PANEL,
    help="Update Configuration Settings Interactively",
)(config.update)
app.command(
    "config set", rich_help_panel=CONFIG_PANEL, help="Set Configuration Values"
)(config.set_config)
app.command(
    "config validate", rich_help_panel=CONFIG_PANEL, help="Validate Configuration"
)(config.validate)
app.command(
    "config delete", rich_help_panel=CONFIG_PANEL, help="Delete Configuration Keys"
)(config.delete_config)

app.add_typer(
    mcp.app,
    name="mcp",
    help="Start MCP Server For AI Integration",
    rich_help_panel=MCP_PANEL,
    hidden=True,
)
app.command(
    "mcp run", rich_help_panel=MCP_PANEL, help="Run The MCP Server With FastMCP CLI"
)(mcp.run)
app.command(
    "mcp dev",
    rich_help_panel=MCP_PANEL,
    help="Run MCP Server In Development Mode With Inspector",
)(mcp.dev)
app.command(
    "mcp inspect", rich_help_panel=MCP_PANEL, help="Inspect MCP Server Capabilities"
)(mcp.inspect)
app.command(
    "mcp fastmcp", rich_help_panel=MCP_PANEL, help="Direct Passthrough To FastMCP CLI"
)(mcp.fastmcp)

app.add_typer(
    info.app,
    name="info",
    help="Resources Commands",
    rich_help_panel=RESOURCES_PANEL,
    hidden=True,
)
app.command(
    "docs", rich_help_panel=RESOURCES_PANEL, help="Open Documentation in Browser"
)(info.docs)
app.command(
    "license", rich_help_panel=RESOURCES_PANEL, help="Display License and Terms"
)(info.license_terms)

app.command("debug", hidden=True)(debug_command)


@app.command(
    "migrate",
    rich_help_panel="Setup",
    help="Migrate legacy ./data/ to global ~/.indexed/data/",
)
def migrate_data(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be migrated without copying"
    ),
) -> None:
    """Migrate legacy local data from ./data/ to global storage."""
    from indexed_config import get_global_root

    from .utils.console import console
    from .utils.migration import has_legacy_data, migrate_legacy_data

    if not has_legacy_data():
        print_info("No legacy data found at ./data/ — nothing to migrate.")
        return

    migrate_legacy_data(get_global_root(), console, dry_run=dry_run)


__all__ = [
    "app",
    "main",
    "DEFAULT_INDEXER",  # noqa: F822
    "svc_create",  # noqa: F822
    "svc_update",  # noqa: F822
    "svc_clear",  # noqa: F822
    "svc_search",  # noqa: F822
    "svc_status",  # noqa: F822
    "SourceConfig",  # noqa: F822
]


def __getattr__(name: str):
    """Lazy load heavy dependencies for tests."""
    if name == "DEFAULT_INDEXER":
        from core.v1.constants import DEFAULT_INDEXER

        return DEFAULT_INDEXER
    elif name == "svc_create":
        from core.v1.engine.services import create

        return create
    elif name == "svc_update":
        from core.v1.engine.services import update

        return update
    elif name == "svc_clear":
        from core.v1.engine.services import clear

        return clear
    elif name == "svc_search":
        from core.v1.engine.services import search

        return search
    elif name == "svc_status":
        from core.v1.engine.services import status

        return status
    elif name == "SourceConfig":
        from core.v1.engine.services import SourceConfig

        return SourceConfig
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def main() -> None:
    """CLI entry point."""
    # Wire logging BEFORE Typer parses args so any third-party module imported
    # during command resolution can't leak to stderr. The Typer callback
    # reconfigures with the resolved verbosity (idempotent).
    bootstrap_logging(
        level="WARNING",
        rich_console=_shared_console,
        theme_styles=THEME_STYLES,
    )

    if len(sys.argv) == 2 and sys.argv[1] in ["--help", "-h"]:
        print_indexed_banner()
    app()


if __name__ == "__main__":
    main()
