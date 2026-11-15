"""``indexed lsp`` — the Language Server Protocol entry point.

The command itself is deliberately thin (resolve storage, hand the facade to the
server); the protocol and the payload builders live in ``indexed.lsp``, where
they are tested without an editor or a terminal.

stdout belongs to the protocol: while the server runs, every other byte on it
would corrupt a frame. Log records already go to stderr, and nothing here
prints.
"""

from __future__ import annotations

import typer


def lsp(ctx: typer.Context) -> None:
    """Serve the index over the Language Server Protocol (stdio).

    An editor speaks LSP to this process: search the knowledge base from the
    symbol palette (``workspace/symbol``) and hover a file to see what the index
    knows about it (``textDocument/hover``). stdio only.

    Examples:
        indexed lsp                     # global storage (~/.indexed)
        indexed --local lsp             # the workspace's .indexed storage
    """
    from indexed.cli.composition import resolve_collections_context
    from indexed.lsp.backend import KnowledgeBackend
    from indexed.lsp.server import serve

    mode_override = ctx.obj.get("mode_override") if ctx.obj else None
    cli_ctx = resolve_collections_context(mode_override=mode_override)
    backend = KnowledgeBackend(str(cli_ctx.collections_path))
    raise typer.Exit(serve(backend))
