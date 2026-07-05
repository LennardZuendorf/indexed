"""Characterization: MCP resource smoke tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.v1.config_models import MCPConfig
from indexed.mcp.server import mcp
from indexed.runtime import resolve_collections_context

COLLECTION_NAME = "mcp-smoke-collection"


@pytest.fixture
def mcp_resource_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write_manifest
):
    monkeypatch.chdir(tmp_path)
    from indexed_config import ensure_storage_dirs, get_local_root

    local_root = get_local_root(tmp_path)
    ensure_storage_dirs(local_root, is_local=True)
    collections_dir = local_root / "data" / "collections"
    write_manifest(collections_dir, COLLECTION_NAME)

    cli_ctx = resolve_collections_context(mode_override="local", workspace=tmp_path)
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
