"""MCP server command for indexed.

Runs the FastMCP server to expose indexed collections to AI agents.
"""

import typer

app = typer.Typer(help="Start MCP server for AI agent integration")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    transport: str = typer.Option(
        "stdio",
        "--transport",
        "-t",
        help="Transport protocol: stdio (default), http, sse, streamable-http"
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        "-h",
        help="Host to bind (HTTP/SSE/streamable-http)"
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="Port to bind (HTTP/SSE/streamable-http)"
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Log level (DEBUG, INFO, WARNING, ERROR)"
    ),
    json_logs: bool = typer.Option(
        False,
        "--json-logs",
        help="Output logs as JSON (structured)"
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
    # Import the MCP server main function
    from cli.mcp import mcp as mcp_server
    from utils.logger import setup_root_logger
    
    # Initialize logging
    setup_root_logger(level_str=log_level.upper(), json_mode=json_logs)
    
    # Run the FastMCP server with parsed arguments
    if transport == "stdio":
        # For stdio, host/port are not applicable
        mcp_server.run()
    elif transport == "http":
        mcp_server.run(transport="http", host=host, port=port, log_level=log_level)
    elif transport == "sse":
        mcp_server.run(transport="sse", host=host, port=port, log_level=log_level)
    elif transport == "streamable-http":
        mcp_server.run(transport="streamable-http", host=host, port=port, log_level=log_level)
    else:
        typer.echo(f"❌ Error: Unsupported transport: {transport}", err=True)
        raise typer.Exit(1)
