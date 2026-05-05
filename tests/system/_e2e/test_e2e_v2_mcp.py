"""End-to-end test that boots the FastMCP server with engine=v2 and queries it.

Closes the spec done-criterion that "MCP server with [general] engine = v2 in
config serves v2 collections to AI agents" — exercises the create-via-CLI →
serve-via-MCP path with the real embedder, FAISS, and LlamaIndex stack.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Coroutine, Generator, TypeVar

import pytest
from fastmcp import Client
from typer.testing import CliRunner

from indexed.app import app
from indexed_config import ConfigService

T = TypeVar("T")

runner = CliRunner()


@pytest.fixture(scope="module")
def v2_mcp_workspace(
    tmp_path_factory: pytest.TempPathFactory, e2e_docs: Path
) -> Generator[Path, None, None]:
    """Create a v2 workspace with `[general] engine = "v2"` and seed a collection."""
    workspace = tmp_path_factory.mktemp("v2_mcp_workspace")
    indexed_dir = workspace / ".indexed"
    indexed_dir.mkdir()
    (indexed_dir / "config.toml").write_text(
        '[general]\nengine = "v2"\n'
        '[core.v2.embedding]\nmodel_name = "all-MiniLM-L6-v2"\n'
        "[core.v2.indexing]\nchunk_size = 512\n"
        '[core.v2.storage]\nvector_store = "faiss"\n'
        "[core.v2.search]\nmax_docs = 10\n",
        encoding="utf-8",
    )
    ConfigService.reset()

    original_cwd = os.getcwd()
    try:
        os.chdir(workspace)
        result = runner.invoke(
            app,
            [
                "--engine",
                "v2",
                "index",
                "create",
                "files",
                "--collection",
                "v2-mcp-test",
                "--path",
                str(e2e_docs),
                "--force",
                "--local",
            ],
        )
        assert result.exit_code == 0, f"Seeding v2 collection failed: {result.stdout}"
    finally:
        os.chdir(original_cwd)

    yield workspace


@pytest.fixture
def mcp_v2_chdir(
    v2_mcp_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Path, None, None]:
    """Chdir into the v2 workspace and reset the ConfigService singleton.

    The MCP server's lifespan reads `[general] engine` from the active
    ConfigService at startup, so a fresh instance bound to the workspace
    is required for the in-memory client to see engine=v2.
    """
    monkeypatch.chdir(v2_mcp_workspace)
    monkeypatch.setenv("INDEXED__storage__mode", "local")
    ConfigService.reset()
    try:
        yield v2_mcp_workspace
    finally:
        ConfigService.reset()


def _run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


class TestV2MCPServer:
    """End-to-end MCP server tests with engine=v2."""

    def test_search_tool_returns_v2_results(self, mcp_v2_chdir: Path) -> None:
        """search tool routes to v2 and returns results from the v2 collection."""
        from indexed.mcp.server import mcp

        async def go() -> Any:
            async with Client(mcp) as client:
                return await client.call_tool(
                    "search", {"query": "semantic search embeddings"}
                )

        response = _run(go())
        payload = _extract_payload(response)
        assert "error" not in payload, f"search returned error: {payload}"
        assert payload["query"] == "semantic search embeddings"
        assert "results" in payload

    def test_search_collection_tool_targets_v2_collection(
        self, mcp_v2_chdir: Path
    ) -> None:
        """search_collection tool reaches the v2 collection by name."""
        from indexed.mcp.server import mcp

        async def go() -> Any:
            async with Client(mcp) as client:
                return await client.call_tool(
                    "search_collection",
                    {"collection": "v2-mcp-test", "query": "indexing pipeline"},
                )

        response = _run(go())
        payload = _extract_payload(response)
        assert "error" not in payload, f"search_collection returned error: {payload}"
        assert payload["query"] == "indexing pipeline"

    def test_collections_resource_lists_v2_collection(self, mcp_v2_chdir: Path) -> None:
        """resource://collections lists v2 collections present on disk."""
        from indexed.mcp.server import mcp

        async def go() -> Any:
            async with Client(mcp) as client:
                return await client.read_resource("resource://collections")

        result = _run(go())
        contents = _resource_text(result)
        parsed = json.loads(contents)
        assert "v2-mcp-test" in parsed.get("collections", []), (
            f"v2 collection not in resource payload: {parsed}"
        )


def _extract_payload(response: object) -> dict[str, Any]:
    """Pull the JSON payload from a FastMCP CallToolResult."""
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    structured = getattr(response, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    content = getattr(response, "content", None)
    if content:
        text = getattr(content[0], "text", None)
        if text:
            parsed: dict[str, Any] = json.loads(text)
            return parsed
    raise AssertionError(f"Could not extract payload from response: {response!r}")


def _resource_text(result: object) -> str:
    """Pull the text payload from a FastMCP read_resource result."""
    if isinstance(result, list) and result:
        text = getattr(result[0], "text", None)
        if text:
            return str(text)
    contents = getattr(result, "contents", None)
    if contents:
        text = getattr(contents[0], "text", None) or getattr(
            contents[0], "content", None
        )
        if text:
            return str(text)
    raise AssertionError(f"Could not extract text from resource result: {result!r}")
