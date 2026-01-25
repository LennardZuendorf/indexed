"""Indexed CLI application - stateless commands backed by services."""

# Fix OpenMP threading issues on macOS before any imports
# Must be set before PyTorch/sentence-transformers are loaded
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import warnings

warnings.filterwarnings("ignore", message="builtin type Swig.*")
import sys  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Optional  # noqa: E402

import typer  # noqa: E402
import typer.rich_utils  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.theme import Theme  # noqa: E402

from .utils.banner import print_indexed_banner  # noqa: E402
from .utils.components import print_success  # noqa: E402
from .utils.components.theme import (  # noqa: E402
    get_accent_style,
    get_help_theme_styles,
)
from .utils.logging import setup_root_logger  # noqa: E402

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


def _parse_early_storage_flags() -> tuple[bool, bool]:
    """Parse and remove --local/--global flags from sys.argv before Typer processes them."""
    use_local, use_global = False, False
    new_argv = [sys.argv[0]]

    for arg in sys.argv[1:]:
        if arg == "--local":
            use_local = True
        elif arg == "--global":
            use_global = True
        else:
            new_argv.append(arg)

    sys.argv[:] = new_argv
    return use_local, use_global


_EARLY_USE_LOCAL, _EARLY_USE_GLOBAL = False, False
from .utils.console import console as _prompt_console  # noqa: E402


@app.callback(invoke_without_command=True)
def _init_app(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose (INFO) logging",
        rich_help_panel="Logging",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Set logging level (DEBUG, INFO, WARNING, ERROR)",
        case_sensitive=False,
        show_choices=True,
        rich_help_panel="Logging",
    ),
    json_logs: bool = typer.Option(
        False, "--json-logs", help="Output logs as JSON", rich_help_panel="Logging"
    ),
) -> None:
    """Initialize logging and handle storage flags. ConfigService is deferred to commands."""
    global _EARLY_USE_LOCAL, _EARLY_USE_GLOBAL

    if (
        ctx.invoked_subcommand is None
        and not ctx.resilient_parsing
        and ("--help" in sys.argv or "-h" in sys.argv)
    ):
        print_indexed_banner()

    env_level = os.getenv("INDEXED_LOG_LEVEL")
    level = (
        (log_level or ("INFO" if verbose else None) or env_level).upper()
        if (log_level or verbose or env_level)
        else None
    )
    json_mode = json_logs or os.getenv("INDEXED_LOG_JSON", "false").lower() == "true"
    setup_root_logger(level_str=level, json_mode=json_mode)

    use_local, use_global = _EARLY_USE_LOCAL, _EARLY_USE_GLOBAL

    if use_local and use_global:
        _prompt_console.print(
            "[red]Error:[/red] Cannot use both --local and --global flags together."
        )
        raise typer.Exit(1)

    if use_local:
        from indexed_config import ensure_storage_dirs, get_local_root, has_local_config

        workspace = Path.cwd()
        if not has_local_config(workspace):
            local_root = get_local_root(workspace)
            ensure_storage_dirs(local_root)
            (local_root / "config.toml").write_text(
                "# Indexed Local Configuration\n"
                "# Auto-created with --local flag\n\n"
                "[storage]\n"
                'mode = "local"\n'
            )
            print_success(f"Created local .indexed folder at {local_root}")


from . import config, info, knowledge, mcp  # noqa: E402

KNOWLEDGE_PANEL = "Knowledge / Index Management"
CONFIG_PANEL = "Configuration Management"
MCP_PANEL = "MCP Server"
RESOURCES_PANEL = "Resources"

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


@app.command(
    "migrate",
    rich_help_panel=CONFIG_PANEL,
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
        console.print(
            "[dim]No legacy data found at ./data/[/dim]\n[dim]Nothing to migrate.[/dim]"
        )
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
    """Initialize CLI, parse storage flags, and run app."""
    global _EARLY_USE_LOCAL, _EARLY_USE_GLOBAL
    _EARLY_USE_LOCAL, _EARLY_USE_GLOBAL = _parse_early_storage_flags()

    if len(sys.argv) == 2 and sys.argv[1] in ["--help", "-h"]:
        print_indexed_banner()
    app()


if __name__ == "__main__":
    main()
