"""The Language Server surface of indexed (``indexed lsp``).

Tier 0 scope: a stdio server that answers ``initialize``, ``workspace/symbol``
and ``textDocument/hover`` from the same on-disk collections the CLI and MCP
server read. It is not a type checker and does not resolve scope — it reports
what the index knows, with the same provenance vocabulary as the
``indexed.search/1`` payload.
"""

from .server import LanguageServer, serve

__all__ = ["LanguageServer", "serve"]
