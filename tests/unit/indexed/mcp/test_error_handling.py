"""Tests for IndexedError handling at MCP tool/resource boundaries."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from indexed.config.errors import ConfigurationError, StorageError

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
    def test_search_returns_envelope_for_unexpected_error(
        self,
        mock_resolve_config: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """A non-IndexedError (e.g. AttributeError from a malformed manifest)
        must still be wrapped in a structured mcp_error_envelope, not escape
        as a raw MCP protocol error.
        """
        mock_resolve_config.return_value = MagicMock()
        mock_search.side_effect = AttributeError(
            "'NoneType' object has no attribute 'x'"
        )

        search_tool = _get_tool("search")
        result = search_tool.fn("test query")

        assert result == {
            "error": "Internal error: 'NoneType' object has no attribute 'x'",
            "type": "MCPError",
        }


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
    def test_search_collection_returns_envelope_for_unexpected_error(
        self,
        mock_resolve_config: MagicMock,
        mock_status: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """A non-IndexedError raised during the actual search (after status
        resolution succeeded) must still be wrapped in a structured envelope.
        """
        mock_resolve_config.return_value = MagicMock()
        mock_status_item = MagicMock()
        mock_status_item.indexers = ["default_indexer"]
        mock_status_item.source_type = None
        mock_status.return_value = [mock_status_item]
        mock_search.side_effect = RuntimeError("unexpected failure")

        search_collection_tool = _get_tool("search_collection")
        result = search_collection_tool.fn("my_collection", "test query")

        assert result == {
            "error": "Internal error: unexpected failure",
            "type": "MCPError",
        }


class TestSourceTypeWhitelisting:
    """Tests for F23: unknown source_type values must not raise ValidationError."""

    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "_resolve_config")
    def test_invalid_source_type_falls_back_and_returns_envelope(
        self,
        mock_resolve_config: MagicMock,
        mock_status: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """A corrupt/legacy source_type in the manifest must not raise ValidationError.

        Before the fix, SourceConfig(type="legacy_corrupt") raised pydantic
        ValidationError which escaped the narrow ``except IndexedError`` clause,
        crashing the tool call.  After the fix the type is whitelisted and falls
        back to "localFiles", so a subsequent IndexedError from the search is
        still caught and wrapped in the graceful error envelope.
        """
        mock_resolve_config.return_value = MagicMock()
        mock_status_item = MagicMock()
        mock_status_item.indexers = ["default_indexer"]
        mock_status_item.source_type = (
            "legacy_corrupt_type"  # not in SourceConfig Literal
        )
        mock_status.return_value = [mock_status_item]
        mock_search.side_effect = StorageError("collection unreadable")

        search_collection_tool = _get_tool("search_collection")
        result = search_collection_tool.fn("my_collection", "test query")

        assert result == {
            "error": "collection unreadable",
            "type": "StorageError",
        }

    @patch.object(tools_module, "_run_search")
    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "_resolve_config")
    def test_status_failure_surfaces_error_envelope(
        self,
        mock_resolve_config: MagicMock,
        mock_status: MagicMock,
        mock_run_search: MagicMock,
    ) -> None:
        """If ``svc_status`` raises an unexpected error (e.g. AttributeError
        from a malformed manifest), search_collection must surface a
        structured error envelope instead of silently fabricating a
        DEFAULT_INDEXER / "localFiles" source_config and searching it.
        """
        mock_resolve_config.return_value = MagicMock()
        mock_status.side_effect = AttributeError("status backend down")

        search_collection_tool = _get_tool("search_collection")
        result = search_collection_tool.fn("my_collection", "test query")

        assert result == {
            "error": "Internal error: status backend down",
            "type": "MCPError",
        }
        mock_run_search.assert_not_called()

    @patch.object(tools_module, "_run_search")
    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "_resolve_config")
    def test_status_indexed_error_surfaces_error_envelope(
        self,
        mock_resolve_config: MagicMock,
        mock_status: MagicMock,
        mock_run_search: MagicMock,
    ) -> None:
        """If ``svc_status`` raises an IndexedError (e.g. a genuinely
        not-found or corrupt collection), search_collection must surface it
        via mcp_error_envelope rather than fabricating a default indexer.
        """
        mock_resolve_config.return_value = MagicMock()
        mock_status.side_effect = StorageError("collection manifest corrupt")

        search_collection_tool = _get_tool("search_collection")
        result = search_collection_tool.fn("my_collection", "test query")

        assert result == {
            "error": "collection manifest corrupt",
            "type": "StorageError",
        }
        mock_run_search.assert_not_called()

    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "svc_status")
    @patch.object(tools_module, "_resolve_config")
    def test_real_collection_still_searches_normally(
        self,
        mock_resolve_config: MagicMock,
        mock_status: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """A resolvable collection must still search normally end-to-end —
        removing the fabricated fallback must not break the legitimate path.
        """
        mock_resolve_config.return_value = MagicMock()
        mock_status_item = MagicMock()
        mock_status_item.indexers = ["real_indexer"]
        mock_status_item.source_type = "localFiles"
        mock_status.return_value = [mock_status_item]
        mock_search.return_value = {}

        search_collection_tool = _get_tool("search_collection")
        result = search_collection_tool.fn("my_collection", "test query")

        assert "error" not in result
        mock_search.assert_called_once()
        source_configs = mock_search.call_args.kwargs["configs"]
        assert source_configs[0].indexer == "real_indexer"
        assert source_configs[0].type == "localFiles"


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
    def test_collection_status_returns_envelope_for_unexpected_error(
        self,
        mock_resolve_config: MagicMock,
        mock_status: MagicMock,
    ) -> None:
        """A non-IndexedError (e.g. AttributeError from a malformed manifest)
        must still be wrapped in a structured mcp_error_envelope, not escape
        as a raw MCP protocol error.
        """
        mock_resolve_config.return_value = MagicMock()
        mock_status.side_effect = AttributeError(
            "'NoneType' object has no attribute 'y'"
        )

        template = _get_template("resource://collection/{name}")
        result = run_async(template.fn(name="my_collection"))

        assert result == {
            "error": "Internal error: 'NoneType' object has no attribute 'y'",
            "type": "MCPError",
        }
