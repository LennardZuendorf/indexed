"""Characterization: MCP `search` tool smoke against a real seeded collection.

Complements ``test_mcp_smoke.py`` (which covers the collection *resources*) by
driving the MCP ``search`` *tool* in-process against a collection built with the
real engine (real FAISS + embeddings), asserting a known document comes back.
This is the behavior-net proof that the agent-facing surface returns real hits.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.conftest import model_available

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

COLLECTION = "mcp-search-net"


def _get_tool(name: str):
    from indexed.mcp.server import mcp

    return asyncio.run(mcp.get_tool(name))


@pytest.fixture
def _no_response_cache():
    """Drop ResponseCachingMiddleware so the tool result is not cached."""
    from fastmcp.server.middleware.caching import ResponseCachingMiddleware

    from indexed.mcp.server import mcp

    original = list(mcp.middleware)
    mcp.middleware = [
        m for m in original if not isinstance(m, ResponseCachingMiddleware)
    ]
    yield
    mcp.middleware = original


def test_mcp_search_tool_returns_seeded_hit(
    local_workspace, files_corpus: Path, build_collection, _no_response_cache
) -> None:
    from unittest.mock import MagicMock

    from connectors.files.connector import FileSystemConnector
    from core.v1.config_models import CoreV1SearchConfig
    from indexed.composition import resolve_collections_context

    # Seed a real, searchable collection at the local workspace's path.
    connector = FileSystemConnector(path=str(files_corpus), include_patterns=["*.txt"])
    build_collection(
        local_workspace.collections_dir,
        COLLECTION,
        connector.reader,
        connector.converter,
    )

    cli_ctx = resolve_collections_context(
        mode_override="local", workspace=local_workspace.root
    )

    # A lifespan-shaped context passed straight to the tool fn (mirrors how
    # FastMCP injects it), so the tool searches the seeded collection.
    tool_ctx = MagicMock()
    tool_ctx.lifespan_context = {
        "cli_context": cli_ctx,
        "search_config": CoreV1SearchConfig(),
    }

    # Fetch the tool BEFORE any context is active (get_tool must not await a mock).
    search_tool = _get_tool("search")
    result = search_tool.fn(
        "penguin migration survey Antarctic coastline", ctx=tool_ctx
    )

    assert result["query"].startswith("penguin migration")
    assert result["total_collections_searched"] >= 1
    assert result["results"], "MCP search tool returned no results for a seeded hit"
    top = result["results"][0]
    assert top["document_id"].endswith("needle.txt"), (
        f"expected needle.txt as top MCP hit, got {top['document_id']!r}"
    )
    assert top["collection"] == COLLECTION
