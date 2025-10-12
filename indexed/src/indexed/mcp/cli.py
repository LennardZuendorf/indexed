"""MCP server command for indexed.

Runs the FastMCP server to expose indexed collections to AI agents.
"""

import typer
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

app = typer.Typer(help="Start MCP server for AI agent integration")


# Helper functions
def _get_server_path() -> str:
    """Get absolute path to the MCP server file."""
    return str(Path(__file__).parent / "server.py")


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
    """Build FastMCP CLI command with all options."""
    cmd = ["fastmcp", subcommand, _get_server_path()]

    # Transport and server options
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

    # Environment options
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
    if inspector_version:
        cmd.extend(["--inspector-version", inspector_version])
    if ui_port:
        cmd.extend(["--ui-port", str(ui_port)])
    if server_port:
        cmd.extend(["--server-port", str(server_port)])

    # Inspect-specific options
    if format:
        cmd.extend(["--format", format])
    if output:
        cmd.extend(["-o", output])

    return cmd


def _execute_fastmcp(cmd: List[str]) -> None:
    """Execute FastMCP CLI command with proper error handling."""
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"❌ Error running FastMCP CLI: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo(
            "❌ Error: FastMCP CLI not found. Please install it with: pip install fastmcp",
            err=True,
        )
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
    # Delegate to run command
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
        None, "--format", help="Output format: text, fastmcp, or mcp"
    ),
    output: Optional[str] = typer.Option(
        None, "-o", "--output", help="Output file path"
    ),
):
    """Inspect MCP server capabilities and generate reports.

    Examples:
        indexed mcp inspect
        indexed mcp inspect --format mcp -o manifest.json
    """
    cmd = _build_fastmcp_command(
        "inspect",
        format=format,
        output=output,
    )

    _execute_fastmcp(cmd)


# FastMCP passthrough command
@app.command("fastmcp")
def fastmcp(
    args: List[str] = typer.Argument(..., help="Arguments to pass to FastMCP CLI"),
):
    """Direct passthrough to FastMCP CLI.

    Examples:
        indexed mcp fastmcp version
        indexed mcp fastmcp install cursor server.py
    """
    cmd = ["fastmcp"] + args
    _execute_fastmcp(cmd)


def cli_main():
    """Entry point for the CLI application."""
    app(sys.argv[1:])


if __name__ == "__main__":
    cli_main()
