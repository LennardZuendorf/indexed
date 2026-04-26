"""MCP server command for indexed.

Runs the FastMCP server to expose indexed collections to AI agents.
"""

import asyncio
import json
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

from ..utils.components import (
    create_key_value_panel,
    create_summary,
    get_heading_style,
    print_error,
    print_success,
)
from ..utils.console import console

app = typer.Typer(help="Start MCP server for AI agent integration")


def _get_server_path() -> str:
    """Get absolute path to the MCP server file."""
    return str(Path(__file__).parent / "server.py")


def _build_inspect_summary(
    name: str,
    fastmcp_version: str,
    mcp_version: str,
    tools: List[Any],
    resources: List[Any],
    templates: List[Any],
    prompts: List[Any],
) -> Dict[str, Any]:
    """Build a summary dict from in-memory FastMCP component lists."""
    return {
        "name": name,
        "fastmcp_version": fastmcp_version,
        "mcp_version": mcp_version,
        "website_url": None,
        "tools_count": len(tools),
        "resources_count": len(resources) + len(templates),
        "prompts_count": len(prompts),
        "templates_count": len(templates),
    }


def _print_inspect_heading() -> None:
    console.print()
    console.print(
        f"[{get_heading_style()}]MCP Server Inspection[/{get_heading_style()}]"
    )
    console.print()


def _print_inspect_summary(summary: Dict[str, Any]) -> None:
    total = (
        summary["tools_count"] + summary["resources_count"] + summary["prompts_count"]
    )
    console.print(
        create_summary(
            "MCP Server",
            f"{total} components ({summary['tools_count']} tools, "
            f"{summary['resources_count']} resources, "
            f"{summary['prompts_count']} prompts, "
            f"{summary['templates_count']} templates)",
        )
    )
    console.print()


def _display_mcp_inspect(summary: Dict[str, Any]) -> None:
    """Render inspection summary as standard panels."""
    _print_inspect_heading()

    server_rows = [
        ("Name", "", summary["name"]),
        ("FastMCP Version", "", summary["fastmcp_version"]),
        ("MCP Standard Version", "", summary["mcp_version"]),
        ("Website", "", summary["website_url"] or "(not set)"),
    ]
    console.print(
        create_key_value_panel(
            "Server Info",
            server_rows,
            category_width=22,
            key_width=0,
            value_max_len=50,
            show_category=True,
            show_headers=False,
            expand=False,
        )
    )
    console.print()

    mcp_rows = [
        ("Available Tools", "", str(summary["tools_count"])),
        ("Available Resources", "", str(summary["resources_count"])),
        ("Available Prompts", "", str(summary["prompts_count"])),
        ("Available Templates", "", str(summary["templates_count"])),
    ]
    console.print(
        create_key_value_panel(
            "MCP Components",
            mcp_rows,
            category_width=22,
            key_width=0,
            value_max_len=50,
            show_category=True,
            show_headers=False,
            expand=False,
        )
    )
    console.print()

    _print_inspect_summary(summary)


def _display_mcp_inspect_json(summary: Dict[str, Any]) -> None:
    """Render inspection summary as JSON for simple-output mode."""
    from rich.syntax import Syntax

    _print_inspect_heading()
    json_str = json.dumps(summary, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", background_color="default")
    console.print(syntax)
    console.print()
    _print_inspect_summary(summary)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    transport: str = typer.Option(
        "stdio",
        "--transport",
        "-t",
        help="Transport protocol: stdio (default), http, sse, streamable-http",
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", "-h", help="Host to bind (HTTP/SSE/streamable-http)"
    ),
    port: int = typer.Option(
        8000, "--port", "-p", help="Port to bind (HTTP/SSE/streamable-http)"
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Log level (DEBUG, INFO, WARNING, ERROR)"
    ),
) -> None:
    """Start the MCP server for AI agent integration.

    Examples:
        # Start with stdio (for Claude Desktop, etc.)
        indexed mcp

        # Start HTTP server
        indexed mcp --transport http --port 8000

        # Start with debug logging
        indexed mcp --log-level DEBUG
    """
    if ctx.invoked_subcommand is None:
        run_impl(transport=transport, host=host, port=port, log_level=log_level)


def run_impl(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    log_level: str = "INFO",
    show_banner: bool = True,
) -> None:
    """Run the MCP server using FastMCP Python API directly."""
    from .server import mcp

    if transport == "stdio":
        mcp.run(transport="stdio", show_banner=show_banner, log_level=log_level)
    else:
        mcp.run(
            transport=transport,  # type: ignore[arg-type]
            show_banner=show_banner,
            host=host,
            port=port,
            log_level=log_level,
        )


@app.command("run")
def run(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        "-t",
        help="Transport protocol: stdio (default), http, sse, streamable-http",
    ),
    host: str = typer.Option(
        "127.0.0.1", "--host", "-h", help="Host to bind (HTTP/SSE/streamable-http)"
    ),
    port: int = typer.Option(
        8000, "--port", "-p", help="Port to bind (HTTP/SSE/streamable-http)"
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Log level (DEBUG, INFO, WARNING, ERROR)"
    ),
    no_banner: bool = typer.Option(
        False, "--no-banner", help="Disable the startup banner display"
    ),
) -> None:
    """Run the MCP server.

    Examples:
        indexed mcp run
        indexed mcp run --transport http --port 8000
        indexed mcp run --log-level DEBUG
    """
    run_impl(
        transport=transport,
        host=host,
        port=port,
        log_level=log_level,
        show_banner=not no_banner,
    )


def dev_impl(
    ui_port: Optional[int] = None,
    server_port: Optional[int] = None,
    inspector_version: Optional[str] = None,
) -> None:
    """Launch MCP Inspector against the indexed server via fastmcp dev inspector.

    Invokes fastmcp via `python -m fastmcp.cli` so the running interpreter's
    site-packages is used — works whether indexed is installed as a uv tool
    (isolated venv, `fastmcp` console script not on PATH) or run from the
    workspace via `uv run`. Server discovery relies on `fastmcp.json` at the
    repo root; run this command from the repo root.
    """
    cmd: List[str] = [sys.executable, "-m", "fastmcp.cli", "dev", "inspector"]
    if ui_port is not None:
        cmd.extend(["--ui-port", str(ui_port)])
    if server_port is not None:
        cmd.extend(["--server-port", str(server_port)])
    if inspector_version is not None:
        cmd.extend(["--inspector-version", inspector_version])

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print_error(f"fastmcp dev exited with error: {e}")
        raise typer.Exit(1)
    except FileNotFoundError:
        print_error(
            "Python interpreter or fastmcp module not found. "
            "Reinstall the indexed wheel."
        )
        raise typer.Exit(1)


@app.command("dev")
def dev(
    ui_port: Optional[int] = typer.Option(
        None, "--ui-port", help="Port for the MCP Inspector UI"
    ),
    server_port: Optional[int] = typer.Option(
        None, "--server-port", help="Port for the MCP Inspector Proxy server"
    ),
    inspector_version: Optional[str] = typer.Option(
        None, "--inspector-version", help="Version of the MCP Inspector to use"
    ),
) -> None:
    """Run MCP server in development mode with MCP Inspector.

    Examples:
        indexed mcp dev
        indexed mcp dev --ui-port 3000 --server-port 8001
    """
    dev_impl(
        ui_port=ui_port,
        server_port=server_port,
        inspector_version=inspector_version,
    )


def inspect_impl() -> None:
    """Inspect MCP server capabilities by introspecting the in-memory mcp object."""
    from .server import mcp

    try:
        import fastmcp as fastmcp_pkg
        import mcp as mcp_pkg

        async def gather() -> Dict[str, Any]:
            tools = await mcp.list_tools()
            resources = await mcp.list_resources()
            templates = await mcp.list_resource_templates()
            prompts = await mcp.list_prompts()
            return {
                "tools": tools,
                "resources": resources,
                "templates": templates,
                "prompts": prompts,
            }

        components = asyncio.run(gather())
        summary = _build_inspect_summary(
            name=mcp.name,
            fastmcp_version=getattr(fastmcp_pkg, "__version__", "Unknown"),
            mcp_version=getattr(mcp_pkg, "__version__", "Unknown"),
            tools=components["tools"],
            resources=components["resources"],
            templates=components["templates"],
            prompts=components["prompts"],
        )
    except Exception as e:
        print_error(f"Failed to inspect MCP server: {e}")
        raise typer.Exit(1)

    from ..utils.simple_output import is_simple_output

    if is_simple_output():
        _display_mcp_inspect_json(summary)
    else:
        _display_mcp_inspect(summary)


@app.command("inspect")
def inspect() -> None:
    """Inspect MCP server capabilities and display tools, resources, and prompts."""
    inspect_impl()


@app.command("docs", rich_help_panel="Resources")
def docs() -> None:
    """Open MCP documentation in browser."""
    url = "https://indexed.ignitr.dev/docs/mcp"
    try:
        webbrowser.open(url)
        console.print()
        print_success(f"Opening MCP documentation in browser...\n  {url}")
        console.print()
    except Exception as e:
        console.print()
        print_error(f"Failed to open browser: {e}\nVisit manually: {url}")
        console.print()
        raise typer.Exit(1)


def cli_main() -> None:
    """Entry point for the CLI application."""
    app(sys.argv[1:])


if __name__ == "__main__":
    cli_main()
