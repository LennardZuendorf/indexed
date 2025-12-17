"""MCP server command for indexed.

Runs the FastMCP server to expose indexed collections to AI agents.
"""

import json
import typer
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils.console import console
from ..utils.components import (
    print_success,
    print_error,
    create_key_value_panel,
    get_heading_style,
)

app = typer.Typer(help="Start MCP server for AI agent integration")


# Helper functions
def _get_server_path() -> str:
    """Get absolute path to the MCP server file."""
    return str(Path(__file__).parent / "server.py")


def _parse_fastmcp_inspect_json(json_output: str) -> Optional[Dict[str, Any]]:
    """
    Parse FastMCP `inspect` CLI output and return the contained JSON as a dictionary if present.
    
    Parameters:
        json_output (str): Raw stdout produced by `fastmcp inspect --format fastmcp`.
    
    Returns:
        dict: Parsed JSON object extracted from the output.
        None: If no valid JSON object can be found or parsed.
    """
    # Try direct parsing with strict=False to allow control characters in strings
    try:
        return json.loads(json_output, strict=False)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in output (starts with '{')
    json_start = json_output.find("{")
    if json_start == -1:
        return None

    # Extract from first '{' to end and parse
    json_str = json_output[json_start:]
    try:
        return json.loads(json_str, strict=False)
    except json.JSONDecodeError:
        pass

    return None


def _extract_inspect_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a concise summary of FastMCP inspect output containing server metadata, reported versions, and counts of components.
    
    Parameters:
        data (Dict[str, Any]): Parsed FastMCP inspect JSON.
    
    Returns:
        summary (Dict[str, Any]): Dictionary with the following keys:
            - name (str): Server name or "Unknown" if not provided.
            - website_url (Optional[str]): Server website URL if present.
            - fastmcp_version (str): Reported FastMCP version or "Unknown".
            - mcp_version (str): Reported MCP version or "Unknown".
            - tools_count (int): Number of tools listed.
            - resources_count (int): Number of resources listed.
            - prompts_count (int): Number of prompts listed.
            - templates_count (int): Number of templates listed.
    """
    server = data.get("server", {})
    env = data.get("environment", {})

    return {
        "name": server.get("name", "Unknown"),
        "website_url": server.get("website_url"),
        "fastmcp_version": env.get("fastmcp", "Unknown"),
        "mcp_version": env.get("mcp", "Unknown"),
        "tools_count": len(data.get("tools", [])),
        "resources_count": len(data.get("resources", [])),
        "prompts_count": len(data.get("prompts", [])),
        "templates_count": len(data.get("templates", [])),
    }


def _display_mcp_inspect(data: Dict[str, Any]) -> None:
    """Display MCP server inspection results using standard panel design.

    Args:
        data: Parsed FastMCP inspect JSON data
    """
    summary = _extract_inspect_summary(data)

    console.print()
    console.print(f"[{get_heading_style()}]MCP Server Inspection[/{get_heading_style()}]")
    console.print()

    # Server Info Panel - use 3-column with empty middle to get blue keys
    server_rows = [
        ("Name", "", summary["name"]),
        ("FastMCP Version", "", summary["fastmcp_version"]),
        ("MCP Standard Version", "", summary["mcp_version"]),
        ("Website", "", summary["website_url"] or "(not set)"),
    ]

    server_panel = create_key_value_panel(
        "Server Info",
        server_rows,
        category_width=22,
        key_width=0,
        value_max_len=50,
        show_category=True,
        show_headers=False,
        expand=False,
    )
    console.print(server_panel)
    console.print()

    # MCP Components Panel
    mcp_rows = [
        ("Available Tools", "", str(summary["tools_count"])),
        ("Available Resources", "", str(summary["resources_count"])),
        ("Available Prompts", "", str(summary["prompts_count"])),
        ("Available Templates", "", str(summary["templates_count"])),
    ]

    mcp_panel = create_key_value_panel(
        "MCP Components",
        mcp_rows,
        category_width=22,
        key_width=0,
        value_max_len=50,
        show_category=True,
        show_headers=False,
        expand=False,
    )
    console.print(mcp_panel)
    console.print()


def _display_mcp_inspect_json(data: Dict[str, Any]) -> None:
    """
    Render a concise JSON-formatted summary of MCP server inspection to the console.
    
    Formats a distilled summary extracted from the full FastMCP inspect output, pretty-prints it as indented JSON with syntax highlighting, and writes it to the configured console.
    
    Parameters:
        data: The full parsed FastMCP `inspect` output; only the extracted summary fields are displayed.
    """
    from rich.syntax import Syntax

    summary = _extract_inspect_summary(data)

    console.print()
    console.print(f"[{get_heading_style()}]MCP Server Inspection[/{get_heading_style()}]")
    console.print()

    json_str = json.dumps(summary, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", background_color="default")
    console.print(syntax)
    console.print()


def _build_fastmcp_command(
    subcommand: str,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    log_level: str = "INFO",
    path: Optional[str] = None,
    python: Optional[str] = None,
    with_packages: Optional[List[str]] = None,
    with_requirements: Optional[str] = None,
    with_editable: Optional[str] = None,
    project: Optional[str] = None,
    skip_env: bool = False,
    no_banner: bool = False,
    inspector_version: Optional[str] = None,
    ui_port: Optional[int] = None,
    server_port: Optional[int] = None,
    format: Optional[str] = None,
    output: Optional[str] = None,
    **kwargs,
) -> List[str]:
    """
    Constructs the FastMCP CLI argument list for a specific subcommand using the provided options.
    
    Builds an argv-style list beginning with "fastmcp", the subcommand, and the local server path, then appends flags appropriate to the chosen subcommand:
    - For "run" and "dev": transport, host, port, path, log level, environment/project options, and banner control.
    - For "dev": additionally supports inspector version, UI port, and server port.
    - For "inspect": supports only format and output options.
    
    Parameters:
        subcommand (str): FastMCP subcommand to invoke (e.g., "run", "dev", "inspect").
        transport (str): Transport type for run/dev (default "stdio").
        host (str): Host for run/dev (default "127.0.0.1").
        port (int): Port for run/dev (default 8000).
        log_level (str): Log level for run/dev (default "INFO").
        path (Optional[str]): Application path passed to FastMCP.
        python (Optional[str]): Python executable or interpreter spec for environment creation.
        with_packages (Optional[List[str]]): Extra packages to install into the environment (each added with `--with`).
        with_requirements (Optional[str]): Path to a requirements file to pass with `--with-requirements`.
        with_editable (Optional[str]): Editable package spec passed with `--with-editable`.
        project (Optional[str]): Project directory to pass with `--project`.
        skip_env (bool): If True, include `--skip-env` to avoid creating a virtual environment.
        no_banner (bool): If True, include `--no-banner` to suppress the startup banner.
        inspector_version (Optional[str]): Inspector version for "dev" (passed via `--inspector-version`).
        ui_port (Optional[int]): UI port for "dev" (passed via `--ui-port`).
        server_port (Optional[int]): Server port for "dev" (passed via `--server-port`).
        format (Optional[str]): Output format for "inspect" (passed via `--format`).
        output (Optional[str]): Output file/path for "inspect" (passed via `-o`).
        **kwargs: Ignored additional keyword arguments.
    
    Returns:
        List[str]: The assembled command and arguments ready to be executed (e.g., via subprocess).
    """
    cmd = ["fastmcp", subcommand, _get_server_path()]

    # Run and dev commands: transport and server options
    if subcommand in ("run", "dev"):
        if transport != "stdio":
            cmd.extend(["--transport", transport])
        if host != "127.0.0.1":
            cmd.extend(["--host", host])
        if port != 8000:
            cmd.extend(["--port", str(port)])
        if path:
            cmd.extend(["--path", path])
        if log_level != "INFO":
            cmd.extend(["--log-level", log_level])
        if no_banner:
            cmd.append("--no-banner")

        # Environment options (run and dev only)
        if python:
            cmd.extend(["--python", python])
        if with_packages:
            for package in with_packages:
                cmd.extend(["--with", package])
        if with_requirements:
            cmd.extend(["--with-requirements", with_requirements])
        if with_editable:
            cmd.extend(["--with-editable", with_editable])
        if project:
            cmd.extend(["--project", project])
        if skip_env:
            cmd.append("--skip-env")

    # Dev-specific options
    if subcommand == "dev":
        if inspector_version:
            cmd.extend(["--inspector-version", inspector_version])
        if ui_port:
            cmd.extend(["--ui-port", str(ui_port)])
        if server_port:
            cmd.extend(["--server-port", str(server_port)])

    # Inspect-specific options
    if subcommand == "inspect":
        if format:
            cmd.extend(["--format", format])
        if output:
            cmd.extend(["-o", output])

    return cmd


def _execute_fastmcp(cmd: List[str]) -> None:
    """
    Run the FastMCP CLI command and exit the application on failure.
    
    This executes the provided command list using subprocess.run and, on error,
    reports a user-facing message and terminates the CLI with a non-zero exit code.
    
    Raises:
        typer.Exit: Exit with code 1 if the FastMCP command returns a non-zero status
            or if the FastMCP executable is not found.
    """
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print_error(f"Error running FastMCP CLI: {e}")
        raise typer.Exit(1)
    except FileNotFoundError:
        print_error("FastMCP CLI not found. Please install it with: pip install fastmcp")
        raise typer.Exit(1)


# Common FastMCP flags that can be added to commands
def _get_common_fastmcp_params():
    """Get common FastMCP parameters for commands."""
    return {
        "python": typer.Option(
            None, "--python", help="Python version to use (e.g., 3.11)"
        ),
        "with_packages": typer.Option(
            [],
            "--with",
            help="Additional packages to install (can be used multiple times)",
        ),
        "with_requirements": typer.Option(
            None,
            "--with-requirements",
            help="Requirements file to install dependencies from",
        ),
        "with_editable": typer.Option(
            None,
            "--with-editable",
            "-e",
            help="Directory containing pyproject.toml to install in editable mode",
        ),
        "project": typer.Option(
            None, "--project", help="Run the command within the given project directory"
        ),
        "skip_env": typer.Option(
            False,
            "--skip-env",
            help="Skip environment setup with uv (use when already in a uv environment)",
        ),
        "path": typer.Option(
            None, "--path", help="Path to bind to when using http transport"
        ),
        "no_banner": typer.Option(
            False, "--no-banner", help="Disable the startup banner display"
        ),
    }


# Main callback (backward compatibility)
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
    json_logs: bool = typer.Option(
        False, "--json-logs", help="Output logs as JSON (structured)"
    ),
):
    """Start the MCP server for AI agent integration.

    Examples:
        # Start with stdio (for Claude Desktop, etc.)
        indexed mcp

        # Start HTTP server
        indexed mcp --transport http --port 8000

        # Start with debug logging
        indexed mcp --log-level DEBUG
    """
    # Only run if no subcommand was invoked (e.g., "indexed mcp" without subcommand)
    if ctx.invoked_subcommand is None:
        run_impl(
            transport=transport,
            host=host,
            port=port,
            log_level=log_level,
            json_logs=json_logs,
        )


# Run command implementation
def run_impl(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
    log_level: str = "INFO",
    json_logs: bool = False,
    path: Optional[str] = None,
    python: Optional[str] = None,
    with_packages: Optional[List[str]] = None,
    with_requirements: Optional[str] = None,
    with_editable: Optional[str] = None,
    project: Optional[str] = None,
    skip_env: bool = False,
    no_banner: bool = False,
    **kwargs,
):
    """Run the MCP server using FastMCP CLI."""
    cmd = _build_fastmcp_command(
        "run",
        transport=transport,
        host=host,
        port=port,
        log_level=log_level,
        path=path,
        python=python,
        with_packages=with_packages,
        with_requirements=with_requirements,
        with_editable=with_editable,
        project=project,
        skip_env=skip_env,
        no_banner=no_banner,
        **kwargs,
    )

    if json_logs:
        cmd.append("--json-logs")

    _execute_fastmcp(cmd)


# Run subcommand
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
    json_logs: bool = typer.Option(
        False, "--json-logs", help="Output logs as JSON (structured)"
    ),
    python: Optional[str] = typer.Option(
        None, "--python", help="Python version to use (e.g., 3.11)"
    ),
    with_packages: Optional[List[str]] = typer.Option(
        [], "--with", help="Additional packages to install (can be used multiple times)"
    ),
    with_requirements: Optional[str] = typer.Option(
        None,
        "--with-requirements",
        help="Requirements file to install dependencies from",
    ),
    with_editable: Optional[str] = typer.Option(
        None,
        "--with-editable",
        "-e",
        help="Directory containing pyproject.toml to install in editable mode",
    ),
    project: Optional[str] = typer.Option(
        None, "--project", help="Run the command within the given project directory"
    ),
    skip_env: bool = typer.Option(
        False,
        "--skip-env",
        help="Skip environment setup with uv (use when already in a uv environment)",
    ),
    path: Optional[str] = typer.Option(
        None, "--path", help="Path to bind to when using http transport"
    ),
    no_banner: bool = typer.Option(
        False, "--no-banner", help="Disable the startup banner display"
    ),
):
    """Run the MCP server with FastMCP CLI.

    Examples:
        indexed mcp run
        indexed mcp run --transport http --port 8000
        indexed mcp run --python 3.11 --with pandas
    """
    run_impl(
        transport=transport,
        host=host,
        port=port,
        log_level=log_level,
        json_logs=json_logs,
        path=path,
        python=python,
        with_packages=with_packages,
        with_requirements=with_requirements,
        with_editable=with_editable,
        project=project,
        skip_env=skip_env,
        no_banner=no_banner,
    )


# Transport shortcuts under run
@app.command("stdio", hidden=True)
def run_stdio(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
    log_level: str = typer.Option("INFO", "--log-level", help="Log level"),
    json_logs: bool = typer.Option(False, "--json-logs", help="Output logs as JSON"),
    python: Optional[str] = typer.Option(
        None, "--python", help="Python version to use (e.g., 3.11)"
    ),
    with_packages: Optional[List[str]] = typer.Option(
        [], "--with", help="Additional packages to install (can be used multiple times)"
    ),
    with_requirements: Optional[str] = typer.Option(
        None,
        "--with-requirements",
        help="Requirements file to install dependencies from",
    ),
    with_editable: Optional[str] = typer.Option(
        None,
        "--with-editable",
        "-e",
        help="Directory containing pyproject.toml to install in editable mode",
    ),
    project: Optional[str] = typer.Option(
        None, "--project", help="Run the command within the given project directory"
    ),
    skip_env: bool = typer.Option(
        False,
        "--skip-env",
        help="Skip environment setup with uv (use when already in a uv environment)",
    ),
    path: Optional[str] = typer.Option(
        None, "--path", help="Path to bind to when using http transport"
    ),
    no_banner: bool = typer.Option(
        False, "--no-banner", help="Disable the startup banner display"
    ),
):
    """Run MCP server with stdio transport."""
    run_impl(
        transport="stdio",
        host=host,
        port=port,
        log_level=log_level,
        json_logs=json_logs,
        path=path,
        python=python,
        with_packages=with_packages,
        with_requirements=with_requirements,
        with_editable=with_editable,
        project=project,
        skip_env=skip_env,
        no_banner=no_banner,
    )


@app.command("http", hidden=True)
def run_http(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
    log_level: str = typer.Option("INFO", "--log-level", help="Log level"),
    json_logs: bool = typer.Option(False, "--json-logs", help="Output logs as JSON"),
    python: Optional[str] = typer.Option(
        None, "--python", help="Python version to use (e.g., 3.11)"
    ),
    with_packages: Optional[List[str]] = typer.Option(
        [], "--with", help="Additional packages to install (can be used multiple times)"
    ),
    with_requirements: Optional[str] = typer.Option(
        None,
        "--with-requirements",
        help="Requirements file to install dependencies from",
    ),
    with_editable: Optional[str] = typer.Option(
        None,
        "--with-editable",
        "-e",
        help="Directory containing pyproject.toml to install in editable mode",
    ),
    project: Optional[str] = typer.Option(
        None, "--project", help="Run the command within the given project directory"
    ),
    skip_env: bool = typer.Option(
        False,
        "--skip-env",
        help="Skip environment setup with uv (use when already in a uv environment)",
    ),
    path: Optional[str] = typer.Option(
        None, "--path", help="Path to bind to when using http transport"
    ),
    no_banner: bool = typer.Option(
        False, "--no-banner", help="Disable the startup banner display"
    ),
):
    """Run MCP server with HTTP transport."""
    run_impl(
        transport="http",
        host=host,
        port=port,
        log_level=log_level,
        json_logs=json_logs,
        path=path,
        python=python,
        with_packages=with_packages,
        with_requirements=with_requirements,
        with_editable=with_editable,
        project=project,
        skip_env=skip_env,
        no_banner=no_banner,
    )


@app.command("sse", hidden=True)
def run_sse(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
    log_level: str = typer.Option("INFO", "--log-level", help="Log level"),
    json_logs: bool = typer.Option(False, "--json-logs", help="Output logs as JSON"),
    python: Optional[str] = typer.Option(
        None, "--python", help="Python version to use (e.g., 3.11)"
    ),
    with_packages: Optional[List[str]] = typer.Option(
        [], "--with", help="Additional packages to install (can be used multiple times)"
    ),
    with_requirements: Optional[str] = typer.Option(
        None,
        "--with-requirements",
        help="Requirements file to install dependencies from",
    ),
    with_editable: Optional[str] = typer.Option(
        None,
        "--with-editable",
        "-e",
        help="Directory containing pyproject.toml to install in editable mode",
    ),
    project: Optional[str] = typer.Option(
        None, "--project", help="Run the command within the given project directory"
    ),
    skip_env: bool = typer.Option(
        False,
        "--skip-env",
        help="Skip environment setup with uv (use when already in a uv environment)",
    ),
    path: Optional[str] = typer.Option(
        None, "--path", help="Path to bind to when using http transport"
    ),
    no_banner: bool = typer.Option(
        False, "--no-banner", help="Disable the startup banner display"
    ),
):
    """Run MCP server with SSE transport."""
    run_impl(
        transport="sse",
        host=host,
        port=port,
        log_level=log_level,
        json_logs=json_logs,
        path=path,
        python=python,
        with_packages=with_packages,
        with_requirements=with_requirements,
        with_editable=with_editable,
        project=project,
        skip_env=skip_env,
        no_banner=no_banner,
    )


@app.command("streamable-http", hidden=True)
def run_streamable_http(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
    log_level: str = typer.Option("INFO", "--log-level", help="Log level"),
    json_logs: bool = typer.Option(False, "--json-logs", help="Output logs as JSON"),
    python: Optional[str] = typer.Option(
        None, "--python", help="Python version to use (e.g., 3.11)"
    ),
    with_packages: Optional[List[str]] = typer.Option(
        [], "--with", help="Additional packages to install (can be used multiple times)"
    ),
    with_requirements: Optional[str] = typer.Option(
        None,
        "--with-requirements",
        help="Requirements file to install dependencies from",
    ),
    with_editable: Optional[str] = typer.Option(
        None,
        "--with-editable",
        "-e",
        help="Directory containing pyproject.toml to install in editable mode",
    ),
    project: Optional[str] = typer.Option(
        None, "--project", help="Run the command within the given project directory"
    ),
    skip_env: bool = typer.Option(
        False,
        "--skip-env",
        help="Skip environment setup with uv (use when already in a uv environment)",
    ),
    path: Optional[str] = typer.Option(
        None, "--path", help="Path to bind to when using http transport"
    ),
    no_banner: bool = typer.Option(
        False, "--no-banner", help="Disable the startup banner display"
    ),
):
    """Run MCP server with streamable-http transport."""
    run_impl(
        transport="streamable-http",
        host=host,
        port=port,
        log_level=log_level,
        json_logs=json_logs,
        path=path,
        python=python,
        with_packages=with_packages,
        with_requirements=with_requirements,
        with_editable=with_editable,
        project=project,
        skip_env=skip_env,
        no_banner=no_banner,
    )


# Dev command
@app.command("dev")
def dev(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
    log_level: str = typer.Option("INFO", "--log-level", help="Log level"),
    json_logs: bool = typer.Option(False, "--json-logs", help="Output logs as JSON"),
    python: Optional[str] = typer.Option(
        None, "--python", help="Python version to use (e.g., 3.11)"
    ),
    with_packages: Optional[List[str]] = typer.Option(
        [], "--with", help="Additional packages to install (can be used multiple times)"
    ),
    with_requirements: Optional[str] = typer.Option(
        None,
        "--with-requirements",
        help="Requirements file to install dependencies from",
    ),
    with_editable: Optional[str] = typer.Option(
        None,
        "--with-editable",
        "-e",
        help="Directory containing pyproject.toml to install in editable mode",
    ),
    project: Optional[str] = typer.Option(
        None, "--project", help="Run the command within the given project directory"
    ),
    skip_env: bool = typer.Option(
        False,
        "--skip-env",
        help="Skip environment setup with uv (use when already in a uv environment)",
    ),
    path: Optional[str] = typer.Option(
        None, "--path", help="Path to bind to when using http transport"
    ),
    no_banner: bool = typer.Option(
        False, "--no-banner", help="Disable the startup banner display"
    ),
    inspector_version: Optional[str] = typer.Option(
        None, "--inspector-version", help="Version of the MCP Inspector to use"
    ),
    ui_port: Optional[int] = typer.Option(
        None, "--ui-port", help="Port for the MCP Inspector UI"
    ),
    server_port: Optional[int] = typer.Option(
        None, "--server-port", help="Port for the MCP Inspector Proxy server"
    ),
):
    """Run MCP server in development mode with MCP Inspector.

    Examples:
        indexed mcp dev
        indexed mcp dev --ui-port 3000 --server-port 8001
    """
    cmd = _build_fastmcp_command(
        "dev",
        transport="stdio",  # Dev mode typically uses stdio
        host=host,
        port=port,
        log_level=log_level,
        path=path,
        python=python,
        with_packages=with_packages,
        with_requirements=with_requirements,
        with_editable=with_editable,
        project=project,
        skip_env=skip_env,
        no_banner=no_banner,
        inspector_version=inspector_version,
        ui_port=ui_port,
        server_port=server_port,
    )

    if json_logs:
        cmd.append("--json-logs")

    _execute_fastmcp(cmd)


# Inspect command
@app.command("inspect")
def inspect(
    format: Optional[str] = typer.Option(
        None, "--format", help="Output format: text, fastmcp, or mcp (bypasses custom display)"
    ),
    output: Optional[str] = typer.Option(
        None, "-o", "--output", help="Output file path"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output summary as formatted JSON"
    ),
    raw: bool = typer.Option(
        False, "--raw", help="Output raw FastMCP JSON (full response)"
    ),
):
    """
    Inspect MCP server capabilities and present a report using either a custom panel view or raw/JSON output.
    
    If `format`, `output`, or `raw` is provided, this command delegates directly to the FastMCP CLI and returns its output (optionally writing to `output`). When run without those options, it captures FastMCP's JSON inspection output and either displays a concise panel-based summary or a formatted JSON summary when `json_output` is true. If parsing the FastMCP JSON fails, the command falls back to displaying FastMCP's text output.
    
    Parameters:
        format (Optional[str]): Output format to request from FastMCP ("text", "fastmcp", or "mcp"). When provided, the CLI call is passed through to FastMCP.
        output (Optional[str]): File path to write FastMCP output; when set, the CLI call is passed through to FastMCP.
        json_output (bool): If true and JSON inspection is captured, display a formatted JSON summary instead of the panel view.
        raw (bool): If true, request the full FastMCP JSON response and pass it through unmodified.
    """
    # If user wants raw FastMCP output (format specified or output file), use FastMCP directly
    if format or output or raw:
        effective_format = format if format else ("fastmcp" if raw else None)
        cmd = _build_fastmcp_command(
            "inspect",
            format=effective_format,
            output=output,
        )
        _execute_fastmcp(cmd)
        return

    # Capture FastMCP JSON output for processing
    cmd = _build_fastmcp_command("inspect", format="fastmcp")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # FastMCP outputs to stdout
        raw_output = result.stdout.strip()
        if not raw_output:
            raw_output = result.stderr.strip()

        data = _parse_fastmcp_inspect_json(raw_output)
        if data is None:
            # Fallback: pass through to FastMCP text output
            print_error("Failed to parse JSON, falling back to FastMCP text output:")
            text_cmd = _build_fastmcp_command("inspect", format=None)
            _execute_fastmcp(text_cmd)
            return

        # Display based on requested format
        if json_output:
            _display_mcp_inspect_json(data)
        else:
            _display_mcp_inspect(data)

    except subprocess.CalledProcessError as e:
        # If FastMCP fails, show the error
        print_error(f"FastMCP inspect failed: {e}")
        if e.stderr:
            console.print(e.stderr)
        raise typer.Exit(1)
    except FileNotFoundError:
        print_error("FastMCP CLI not found. Please install it with: pip install fastmcp")
        raise typer.Exit(1)


# FastMCP passthrough command
@app.command("fastmcp")
def fastmcp(
    args: List[str] = typer.Argument(
        None,
        help='Arguments to pass to FastMCP CLI. Use quotes or prefix patterns like arg=, args=, arguments=',
    ),
):
    """Direct passthrough to FastMCP CLI.

    Pass arguments to FastMCP using quotes or prefix patterns:
      - Quoted: "version", "--help", "run --transport http"
      - Prefixed: arg=version, args=--help, arguments=run

    Use 'args=--help' to see FastMCP's help menu.

    Examples:
        indexed mcp fastmcp "version"              # Show FastMCP version
        indexed mcp fastmcp args=--help            # Show FastMCP help
        indexed mcp fastmcp "run" args=--help      # Show FastMCP run help
        indexed mcp fastmcp arg=install arg=cursor # Install for Cursor
        indexed mcp fastmcp "install" "cursor"     # Same as above
    """
    if not args:
        print_error("No arguments provided. Use 'indexed mcp fastmcp args=--help' to see FastMCP help.")
        raise typer.Exit(1)

    # Process arguments - extract values from prefix patterns
    processed_args: List[str] = []
    for arg in args:
        # Check for various prefix patterns
        if arg.startswith("arguments="):
            processed_args.append(arg[10:])
        elif arg.startswith("args="):
            processed_args.append(arg[5:])
        elif arg.startswith("arg="):
            processed_args.append(arg[4:])
        else:
            # Regular argument (quoted or plain)
            processed_args.append(arg)

    cmd = ["fastmcp"] + processed_args
    _execute_fastmcp(cmd)


@app.command("docs", rich_help_panel="Resources")
def docs() -> None:
    """
    Open the MCP server documentation URL in the user's default web browser.
    
    If the browser cannot be opened, prints a manual URL instruction and exits with code 1 by raising typer.Exit.
    
    Raises:
        typer.Exit: with exit code 1 if the browser could not be opened.
    """
    url = "https://indexed.ignitr.dev/docs/mcp"
    try:
        webbrowser.open(url)
        typer.echo()
        print_success("Opening MCP documentation in browser...")
        typer.echo(f"  {url}")
        typer.echo()
    except Exception as e:
        typer.echo()
        print_error(f"Failed to open browser: {e}")
        typer.echo(f"Visit manually: {url}")
        typer.echo()
        raise typer.Exit(1)


def cli_main():
    """Entry point for the CLI application."""
    app(sys.argv[1:])


if __name__ == "__main__":
    cli_main()