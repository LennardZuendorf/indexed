"""Tests for IndexedError handling at MCP tool/resource boundaries."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from indexed_config.errors import ConfigurationError, StorageError

import indexed.mcp.resources as resources_module
import indexed.mcp.tools as tools_module
from indexed.mcp.server import mcp


def run_async(coro_or_result):
    """Run coroutine synchronously or return result directly if not a coroutine."""
    if asyncio.iscoroutine(coro_or_result):
        return asyncio.run(coro_or_result)
    return coro_or_result


def _get_tool(name: str):
    return asyncio.run(mcp.get_tool(name))


def _get_resource(uri: str):
    return asyncio.run(mcp.get_resource(uri))


def _get_template(uri: str):
    return asyncio.run(mcp.get_resource_template(uri))


@pytest.fixture(autouse=True)
def mock_fastmcp_context():
    """Provide a minimal FastMCP Context via contextvar for dependency injection."""
    try:
        from fastmcp.server.context import Context, _current_context

        dummy_server = MagicMock()
        ctx = Context(dummy_server)
        token = _current_context.set(ctx)
        yield ctx
        _current_context.reset(token)
    except Exception:
        yield None


class TestSearchToolErrorHandling:
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_search_returns_envelope_for_indexed_error(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        mock_resolve_config.return_value = MagicMock()
        mock_search.side_effect = ConfigurationError("bad search config")

        search_tool = _get_tool("search")
        result = search_tool.fn("test query")

        assert result == {
            "error": "bad search config",
            "type": "ConfigurationError",
        }

    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_search_propagates_unexpected_error(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        mock_resolve_config.return_value = MagicMock()
        mock_search.side_effect = RuntimeError("unexpected failure")

        search_tool = _get_tool("search")

        with pytest.raises(RuntimeError, match="unexpected failure"):
            search_tool.fn("test query")


class TestSearchCollectionToolErrorHandling:
    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "_resolve_config")
    def test_search_collection_returns_envelope_for_indexed_error(
        self,
        mock_resolve_config: MagicMock,
        mock_status: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        mock_resolve_config.return_value = MagicMock()
        mock_status_item = MagicMock()
        mock_status_item.indexers = ["default_indexer"]
        mock_status_item.source_type = None
        mock_status.return_value = [mock_status_item]
        mock_search.side_effect = StorageError("collection unreadable")

        search_collection_tool = _get_tool("search_collection")
        result = search_collection_tool.fn("my_collection", "test query")

        assert result == {
            "error": "collection unreadable",
            "type": "StorageError",
        }

    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "_resolve_config")
    def test_search_collection_propagates_unexpected_error(
        self,
        mock_resolve_config: MagicMock,
        mock_status: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        mock_resolve_config.return_value = MagicMock()
        mock_status_item = MagicMock()
        mock_status_item.indexers = ["default_indexer"]
        mock_status_item.source_type = None
        mock_status.return_value = [mock_status_item]
        mock_search.side_effect = RuntimeError("unexpected failure")

        search_collection_tool = _get_tool("search_collection")

        with pytest.raises(RuntimeError, match="unexpected failure"):
            search_collection_tool.fn("my_collection", "test query")


class TestResourceErrorHandling:
    @patch.object(resources_module, "svc_status")
    def test_collections_list_returns_envelope_for_indexed_error(
        self,
        mock_status: MagicMock,
    ) -> None:
        mock_status.side_effect = ConfigurationError("status config invalid")

        resource = _get_resource("resource://collections")
        result = run_async(resource.fn())

        assert result == {
            "error": "status config invalid",
            "type": "ConfigurationError",
        }

    @patch.object(resources_module, "svc_status")
    def test_collections_list_propagates_unexpected_error(
        self,
        mock_status: MagicMock,
    ) -> None:
        mock_status.side_effect = RuntimeError("unexpected failure")

        resource = _get_resource("resource://collections")

        with pytest.raises(RuntimeError, match="unexpected failure"):
            run_async(resource.fn())

    @patch.object(resources_module, "svc_status")
    @patch.object(resources_module, "_resolve_config")
    def test_collection_status_returns_envelope_for_indexed_error(
        self,
        mock_resolve_config: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        mock_resolve_config.return_value = MagicMock()
        mock_status.side_effect = StorageError("cannot read collection")

        template = _get_template("resource://collection/{name}")
        result = run_async(template.fn(name="my_collection"))

        assert result == {
            "error": "cannot read collection",
            "type": "StorageError",
        }

    @patch.object(resources_module, "svc_status")
    @patch.object(resources_module, "_resolve_config")
    def test_collection_status_propagates_unexpected_error(
        self,
        mock_resolve_config: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        mock_resolve_config.return_value = MagicMock()
        mock_status.side_effect = RuntimeError("unexpected failure")

        template = _get_template("resource://collection/{name}")

        with pytest.raises(RuntimeError, match="unexpected failure"):
            run_async(template.fn(name="my_collection"))
