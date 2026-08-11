"""System test: the CLI and the MCP lifespan share one collections path.

With the local/global axis gone (workspace-profile/1, R1) there is nothing left
to diverge on — which is exactly what this pins: both sides must land on
``~/.indexed/data/collections`` with no mode argument in sight.
"""

import asyncio
from pathlib import Path

from indexed.config import ensure_storage_dirs, get_global_root, reload
from indexed.cli.composition import resolve_collections_context


def test_cli_and_mcp_lifespan_share_collections_path(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(tmp_path)
    reload()

    ensure_storage_dirs(get_global_root())
    expected = get_global_root() / "data" / "collections"

    cli_ctx = resolve_collections_context(workspace=tmp_path)
    assert cli_ctx.collections_path == expected

    async def run_lifespan():
        from indexed.mcp.server import lifespan, mcp

        async with lifespan(mcp) as state:
            return state["cli_context"].collections_path

    mcp_path = asyncio.run(run_lifespan())

    assert mcp_path == expected
    assert cli_ctx.collections_path == mcp_path
