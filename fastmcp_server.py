"""Entrypoint shim for `fastmcp run`/`fastmcp dev`/`fastmcp install`.

The MCP server lives at `indexed.mcp.server` inside the workspace package.
That module uses package-relative imports, so loading it directly as a
filesystem path would fail. This shim re-exports the server instance via
its absolute import path.
"""

from indexed.mcp.server import mcp

__all__ = ["mcp"]
