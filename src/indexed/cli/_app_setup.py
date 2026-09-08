"""Command registration for the Indexed CLI.

Extracted from ``app.py`` (which keeps the Typer app object, callback, lazy
service loaders, and ``main`` entry point). ``register_commands(app)`` wires
every subcommand/sub-Typer onto the app at import time, so the console-script
entry points (``indexed.cli.app:app`` / ``:main``) see a fully-populated app.
Kept lazy-free of heavy ML imports — these are the same command-module imports
app.py performed at module scope before the split.
"""

from __future__ import annotations

import typer

KNOWLEDGE_PANEL = "Knowledge / Index Management"
CONFIG_PANEL = "Configuration Management"
MCP_PANEL = "MCP Server"
RESOURCES_PANEL = "Resources"


def register_commands(app: typer.Typer) -> None:
    """Register every subcommand and sub-Typer onto ``app`` (idempotent-ish;
    call exactly once at ``app.py`` import time)."""
    from . import info, knowledge
    from .. import mcp
    from indexed.config import cli as config
    from .debug import debug as debug_command
    from .init import init as init_command

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
    app.command(
        "index migrate",
        rich_help_panel=KNOWLEDGE_PANEL,
        help="Migrate a v1 Collection to the v2 Engine",
    )(knowledge.migrate.migrate)

    # Short aliases (hidden — not shown in help)
    app.add_typer(knowledge.create.app, name="create", hidden=True)
    app.command("search", hidden=True)(knowledge.search.search)
    app.command("inspect", hidden=True)(knowledge.inspect.inspect_collections)
    app.command("update", hidden=True)(knowledge.update.update)
    app.command("remove", hidden=True)(knowledge.remove.remove)
    app.command("migrate", hidden=True)(knowledge.migrate.migrate)

    app.add_typer(
        config.app,
        name="config",
        help="Manage Configuration",
        rich_help_panel="Config Management",
        hidden=True,
    )
    app.command(
        "config get", rich_help_panel=CONFIG_PANEL, help="Get A Configuration Value"
    )(config.get_config)
    app.command(
        "config set", rich_help_panel=CONFIG_PANEL, help="Set Configuration Values"
    )(config.set_config)
    app.command(
        "config list", rich_help_panel=CONFIG_PANEL, help="List Resolved Configuration"
    )(config.list_config)
    app.command(
        "config validate", rich_help_panel=CONFIG_PANEL, help="Validate Configuration"
    )(config.validate)

    app.add_typer(
        mcp.app,
        name="mcp",
        help="Start MCP Server For AI Integration",
        rich_help_panel=MCP_PANEL,
        hidden=True,
    )
    app.command("mcp run", rich_help_panel=MCP_PANEL, help="Run The MCP Server")(
        mcp.run
    )
    app.command(
        "mcp dev",
        rich_help_panel=MCP_PANEL,
        help="Run MCP Server In Development Mode With Inspector",
    )(mcp.dev)
    app.command(
        "mcp inspect", rich_help_panel=MCP_PANEL, help="Inspect MCP Server Capabilities"
    )(mcp.inspect)

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
