"""Legacy command group that directly invokes legacy adapter modules."""

from typing import List
import sys
import runpy
import typer


legacy_app = typer.Typer(help="Legacy commands proxied to original scripts")


# Map subcommand keys to original main.legacy.* module names
LEGACY_MAP = {
    "collection-search": "collection_search_cmd_adapter",
    "collection-mcp": "collection_search_mcp_stdio_adapter",
    "collection-update": "collection_update_cmd_adapter",
    "confluence-create": "confluence_collection_create_cmd_adapter",
    "files-create": "files_collection_create_cmd_adapter",
    "jira-create": "jira_collection_create_cmd_adapter",
}


def _run_legacy_subcommand(subcommand: str, forwarded_args: List[str]) -> None:
    """Run the legacy adapter module for the given subcommand.

    Forwards all arguments verbatim and preserves exit status.
    """
    if subcommand not in LEGACY_MAP:
        available = ", ".join(sorted(LEGACY_MAP.keys()))
        typer.echo(f"Unknown legacy subcommand: {subcommand}\nAvailable: {available}")
        raise typer.Exit(2)

    module_name = "main.legacy." + LEGACY_MAP[subcommand]
    # Replace argv for the target module
    sys.argv = [sys.argv[0]] + forwarded_args
    try:
        runpy.run_module(module_name, run_name="__main__")
    except SystemExit as exc:  # Preserve the nested script's exit code
        code = exc.code if isinstance(exc.code, int) else 1
        raise typer.Exit(code)


_ctx_settings = {"allow_extra_args": True, "ignore_unknown_options": True}


@legacy_app.command(
    "collection-search",
    context_settings=_ctx_settings,
    help="Search collections using legacy interface",
)
def legacy_collection_search(ctx: typer.Context) -> None:
    _run_legacy_subcommand("collection-search", list(map(str, ctx.args)))


@legacy_app.command(
    "collection-mcp",
    context_settings=_ctx_settings,
    help="Start MCP server using legacy interface",
)
def legacy_collection_mcp(ctx: typer.Context) -> None:
    _run_legacy_subcommand("collection-mcp", list(map(str, ctx.args)))


@legacy_app.command(
    "collection-update",
    context_settings=_ctx_settings,
    help="Update collections using legacy interface",
)
def legacy_collection_update(ctx: typer.Context) -> None:
    _run_legacy_subcommand("collection-update", list(map(str, ctx.args)))


@legacy_app.command(
    "confluence-create",
    context_settings=_ctx_settings,
    help="Create Confluence collections using legacy interface",
)
def legacy_confluence_create(ctx: typer.Context) -> None:
    _run_legacy_subcommand("confluence-create", list(map(str, ctx.args)))


@legacy_app.command(
    "files-create",
    context_settings=_ctx_settings,
    help="Create file-based collections using legacy interface",
)
def legacy_files_create(ctx: typer.Context) -> None:
    _run_legacy_subcommand("files-create", list(map(str, ctx.args)))


@legacy_app.command(
    "jira-create",
    context_settings=_ctx_settings,
    help="Create Jira collections using legacy interface",
)
def legacy_jira_create(ctx: typer.Context) -> None:
    _run_legacy_subcommand("jira-create", list(map(str, ctx.args)))
