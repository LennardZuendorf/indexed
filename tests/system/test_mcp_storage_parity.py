"""System test: CLI --local and MCP lifespan share the same collections path."""

import asyncio

from indexed_config import ensure_storage_dirs, get_local_root
from indexed.composition import resolve_collections_context


def test_cli_local_and_mcp_lifespan_share_collections_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    local_root = get_local_root(tmp_path)
    ensure_storage_dirs(local_root, is_local=True)
    expected = local_root / "data" / "collections"

    cli_ctx = resolve_collections_context(mode_override="local", workspace=tmp_path)
    assert cli_ctx.collections_path == expected

    async def run_lifespan():
        from indexed.mcp.server import lifespan, mcp

        async with lifespan(mcp) as state:
            return state["cli_context"].collections_path

    mcp_path = asyncio.run(run_lifespan())

    assert mcp_path == expected
    assert cli_ctx.collections_path == mcp_path
