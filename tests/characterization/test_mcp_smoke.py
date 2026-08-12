"""Characterization: MCP resource smoke tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from indexed.core.v1.config_models import MCPConfig
from indexed.mcp.server import mcp
from indexed.cli.composition import resolve_collections_context

COLLECTION_NAME = "mcp-smoke-collection"


@pytest.fixture
def mcp_resource_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write_manifest
):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(tmp_path)
    from indexed.config import ensure_storage_dirs, get_global_root, reload

    reload()
    global_root = get_global_root()
    ensure_storage_dirs(global_root)
    collections_dir = global_root / "data" / "collections"
    write_manifest(collections_dir, COLLECTION_NAME)

    cli_ctx = resolve_collections_context(workspace=tmp_path)
    mcp_config = MCPConfig()

    from fastmcp.server.context import _current_context

    ctx = MagicMock()
    ctx.lifespan_context = {
        "cli_context": cli_ctx,
        "mcp_config": mcp_config,
    }
    token = _current_context.set(ctx)
    yield ctx
    _current_context.reset(token)


def _read_resource_json(uri: str) -> dict[str, object]:
    result = asyncio.run(mcp.read_resource(uri))
    assert result.contents
    return json.loads(result.contents[0].content)


def test_mcp_collections_list_resource_keys(mcp_resource_context) -> None:
    del mcp_resource_context
    payload = _read_resource_json("resource://collections")
    assert "collections" in payload
    assert COLLECTION_NAME in payload["collections"]


def test_mcp_collections_status_resource_keys(mcp_resource_context) -> None:
    del mcp_resource_context
    payload = _read_resource_json("resource://collections/status")
    assert "collections" in payload
    collections = payload["collections"]
    assert isinstance(collections, list)
    assert len(collections) >= 1
    status = collections[0]
    for key in (
        "name",
        "number_of_documents",
        "number_of_chunks",
        "source_type",
        "indexers",
    ):
        assert key in status
