"""Tests for the MCP server implementation."""

import asyncio
from unittest.mock import patch, MagicMock

import pytest

# Import the server module to access the underlying functions
import indexed.mcp.server as server_module
from indexed.mcp.server import (
    mcp,
    get_mcp_config,
    get_search_config,
    _get_mcp_config,
    _get_search_config,
    lifespan,
)


def run_async(coro_or_result):
    """Run coroutine synchronously or return result directly if not a coroutine."""
    if asyncio.iscoroutine(coro_or_result):
        # Use asyncio.run() to create a fresh event loop with proper context
        return asyncio.run(coro_or_result)
    return coro_or_result


@pytest.fixture(autouse=True)
def mock_fastmcp_context():
    """Provide a minimal FastMCP Context via contextvar for dependency injection."""
    try:
        from fastmcp.server.context import _current_context, Context

        # Provide a dummy FastMCP instance; tests don't rely on real server behavior
        dummy_server = MagicMock()
        ctx = Context(dummy_server)
        token = _current_context.set(ctx)
        yield ctx
        _current_context.reset(token)
    except Exception:
        # If FastMCP is unavailable, allow tests to proceed without context
        yield None


class TestServerInstance:
    """Tests for the FastMCP server instance."""

    def test_server_has_name(self) -> None:
        """Test that the server has the correct name."""
        assert mcp.name == "Indexed MCP Server"

    def test_server_has_lifespan(self) -> None:
        """Test that the server has a lifespan configured."""
        # The server should have a lifespan context manager configured
        assert mcp._lifespan is not None

    def test_server_has_middleware(self) -> None:
        """Test that the server has caching middleware configured."""
        # Check that middleware is registered via the middleware property
        assert hasattr(mcp, "middleware")


class TestConfigLoading:
    """Tests for configuration loading functions."""

    def test_get_mcp_config_returns_config(self) -> None:
        """Test that get_mcp_config returns an MCPConfig instance."""
        from core.v1.config_models import MCPConfig

        config = get_mcp_config()
        assert isinstance(config, MCPConfig)

    def test_get_search_config_returns_config(self) -> None:
        """Test that get_search_config returns a CoreV1SearchConfig instance."""
        from core.v1.config_models import CoreV1SearchConfig

        config = get_search_config()
        assert isinstance(config, CoreV1SearchConfig)

    def test_get_mcp_config_fallback_on_error(self) -> None:
        """Test that _get_mcp_config falls back to defaults on error."""
        from core.v1.config_models import MCPConfig

        with patch.object(server_module, "ConfigService") as mock_config:
            mock_config.instance.side_effect = Exception("Config error")
            config = _get_mcp_config()
            assert isinstance(config, MCPConfig)

    def test_get_search_config_fallback_on_error(self) -> None:
        """Test that _get_search_config falls back to defaults on error."""
        from core.v1.config_models import CoreV1SearchConfig

        with patch.object(server_module, "ConfigService") as mock_config:
            mock_config.instance.side_effect = Exception("Config error")
            config = _get_search_config()
            assert isinstance(config, CoreV1SearchConfig)


class TestSearchToolFunction:
    """Tests for the search tool underlying function."""

    @patch.object(server_module, "svc_search")
    @patch.object(server_module, "get_search_config")
    def test_search_returns_results(
        self, mock_get_config: MagicMock, mock_search: MagicMock
    ) -> None:
        """Test that search returns results from the service layer."""
        mock_config = MagicMock()
        mock_config.max_docs = 10
        mock_config.max_chunks = 5
        mock_config.score_threshold = 0.7
        mock_config.include_full_text = False
        mock_config.include_all_chunks = False
        mock_config.include_matched_chunks = True
        mock_get_config.return_value = mock_config

        mock_search.return_value = {
            "collection1": [{"doc": "result1"}],
            "collection2": [{"doc": "result2"}],
        }

        # Access the underlying function through the tool's fn attribute
        search_tool = mcp._tool_manager._tools.get("search")
        assert search_tool is not None
        result = search_tool.fn("test query")

        assert "collection1" in result
        assert "collection2" in result
        mock_search.assert_called_once()

    @patch.object(server_module, "svc_search")
    @patch.object(server_module, "get_search_config")
    def test_search_handles_error(
        self, mock_get_config: MagicMock, mock_search: MagicMock
    ) -> None:
        """Test that search handles errors gracefully."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        mock_search.side_effect = Exception("Search failed")

        search_tool = mcp._tool_manager._tools.get("search")
        assert search_tool is not None
        result = search_tool.fn("test query")

        assert "error" in result
        assert "Search failed" in result["error"]


class TestSearchCollectionToolFunction:
    """Tests for the search_collection tool underlying function."""

    @patch.object(server_module, "svc_search")
    @patch.object(server_module, "svc_status")
    @patch.object(server_module, "get_search_config")
    def test_search_collection_returns_results(
        self,
        mock_get_config: MagicMock,
        mock_status: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """Test that search_collection returns results for a specific collection."""
        mock_config = MagicMock()
        mock_config.max_docs = 10
        mock_config.max_chunks = 5
        mock_config.score_threshold = 0.7
        mock_config.include_full_text = False
        mock_config.include_all_chunks = False
        mock_config.include_matched_chunks = True
        mock_get_config.return_value = mock_config

        mock_status_item = MagicMock()
        mock_status_item.indexers = ["default_indexer"]
        mock_status.return_value = [mock_status_item]

        mock_search.return_value = {"my_collection": [{"doc": "result"}]}

        search_collection_tool = mcp._tool_manager._tools.get("search_collection")
        assert search_collection_tool is not None
        result = search_collection_tool.fn("my_collection", "test query")

        assert "my_collection" in result
        mock_search.assert_called_once()

    @patch.object(server_module, "svc_status")
    @patch.object(server_module, "get_search_config")
    def test_search_collection_not_found(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        """Test that search_collection handles missing collection."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        mock_status.return_value = []

        search_collection_tool = mcp._tool_manager._tools.get("search_collection")
        assert search_collection_tool is not None
        result = search_collection_tool.fn("nonexistent", "test query")

        assert "error" in result
        assert "not found" in result["error"]

    @patch.object(server_module, "svc_search")
    @patch.object(server_module, "svc_status")
    @patch.object(server_module, "get_search_config")
    def test_search_collection_handles_error(
        self,
        mock_get_config: MagicMock,
        mock_status: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """Test that search_collection handles errors gracefully."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config

        mock_status_item = MagicMock()
        mock_status_item.indexers = ["default_indexer"]
        mock_status.return_value = [mock_status_item]

        mock_search.side_effect = Exception("Search failed")

        search_collection_tool = mcp._tool_manager._tools.get("search_collection")
        assert search_collection_tool is not None
        result = search_collection_tool.fn("my_collection", "test query")

        assert "error" in result


class TestCollectionsListResourceFunction:
    """Tests for the collections_list resource underlying function."""

    @patch.object(server_module, "svc_status")
    def test_collections_list_returns_names(self, mock_status: MagicMock) -> None:
        """Test that collections_list returns collection names."""
        mock_status1 = MagicMock()
        mock_status1.name = "collection1"
        mock_status2 = MagicMock()
        mock_status2.name = "collection2"
        mock_status.return_value = [mock_status1, mock_status2]

        template = mcp._resource_manager._templates.get("resource://collections/{_all}")
        assert template is not None
        result = run_async(template.fn("all"))

        assert result == ["collection1", "collection2"]

    @patch.object(server_module, "svc_status")
    def test_collections_list_handles_error(self, mock_status: MagicMock) -> None:
        """Test that collections_list handles errors gracefully."""
        mock_status.side_effect = Exception("Status failed")

        template = mcp._resource_manager._templates.get("resource://collections/{_all}")
        assert template is not None
        result = run_async(template.fn("all"))

        assert len(result) == 1
        assert "error" in result[0]


class TestCollectionsStatusListResourceFunction:
    """Tests for the collections_status_list resource underlying function."""

    @patch.object(server_module, "svc_status")
    @patch.object(server_module, "get_mcp_config")
    def test_collections_status_list_returns_details(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        """Test that collections_status_list returns detailed status."""
        mock_config = MagicMock()
        mock_config.include_index_size = True
        mock_get_config.return_value = mock_config

        mock_status_item = MagicMock()
        mock_status_item.name = "collection1"
        mock_status_item.number_of_documents = 100
        mock_status_item.number_of_chunks = 500
        mock_status_item.updated_time = "2024-01-01T00:00:00"
        mock_status_item.last_modified_document_time = "2024-01-01T00:00:00"
        mock_status_item.indexers = ["indexer1"]
        mock_status_item.index_size = 1024
        mock_status_item.source_type = "files"
        mock_status_item.relative_path = "./docs"
        mock_status_item.disk_size_bytes = 2048
        mock_status.return_value = [mock_status_item]

        template = mcp._resource_manager._templates.get(
            "resource://collections/status/{_all}"
        )
        assert template is not None
        result = run_async(template.fn(_all="all"))

        assert len(result) == 1
        assert result[0]["name"] == "collection1"
        assert result[0]["number_of_documents"] == 100
        assert result[0]["number_of_chunks"] == 500

    @patch.object(server_module, "svc_status")
    @patch.object(server_module, "get_mcp_config")
    def test_collections_status_list_handles_error(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        """Test that collections_status_list handles errors gracefully."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        mock_status.side_effect = Exception("Status failed")

        template = mcp._resource_manager._templates.get(
            "resource://collections/status/{_all}"
        )
        assert template is not None
        result = run_async(template.fn(_all="all"))

        assert len(result) == 1
        assert "error" in result[0]


class TestCollectionStatusResourceTemplateFunction:
    """Tests for the collection_status resource template underlying function."""

    @patch.object(server_module, "svc_status")
    @patch.object(server_module, "get_mcp_config")
    def test_collection_status_returns_details(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        """Test that collection_status returns details for a specific collection."""
        mock_config = MagicMock()
        mock_config.include_index_size = True
        mock_get_config.return_value = mock_config

        mock_status_item = MagicMock()
        mock_status_item.name = "my_collection"
        mock_status_item.number_of_documents = 50
        mock_status_item.number_of_chunks = 250
        mock_status_item.updated_time = "2024-01-01T00:00:00"
        mock_status_item.last_modified_document_time = "2024-01-01T00:00:00"
        mock_status_item.indexers = ["indexer1"]
        mock_status_item.index_size = 512
        mock_status_item.source_type = "jira"
        mock_status_item.relative_path = None
        mock_status_item.disk_size_bytes = 1024
        mock_status.return_value = [mock_status_item]

        template = mcp._resource_manager._templates.get("resource://collections/{name}")
        assert template is not None
        result = run_async(template.fn(name="my_collection"))

        assert result["name"] == "my_collection"
        assert result["number_of_documents"] == 50

    @patch.object(server_module, "svc_status")
    @patch.object(server_module, "get_mcp_config")
    def test_collection_status_not_found(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        """Test that collection_status handles missing collection."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        mock_status.return_value = []

        template = mcp._resource_manager._templates.get("resource://collections/{name}")
        assert template is not None
        result = run_async(template.fn(name="nonexistent"))

        assert "error" in result
        assert "not found" in result["error"]

    @patch.object(server_module, "svc_status")
    @patch.object(server_module, "get_mcp_config")
    def test_collection_status_handles_error(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        """Test that collection_status handles errors gracefully."""
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        mock_status.side_effect = Exception("Status failed")

        template = mcp._resource_manager._templates.get("resource://collections/{name}")
        assert template is not None
        result = run_async(template.fn(name="my_collection"))

        assert "error" in result


class TestToolRegistration:
    """Tests to verify tools are properly registered with FastMCP."""

    def test_search_tool_registered(self) -> None:
        """Test that search tool is registered."""
        tools = mcp._tool_manager._tools
        assert "search" in tools

    def test_search_collection_tool_registered(self) -> None:
        """Test that search_collection tool is registered."""
        tools = mcp._tool_manager._tools
        assert "search_collection" in tools

    def test_search_tool_has_description(self) -> None:
        """Test that search tool has a description."""
        tool = mcp._tool_manager._tools.get("search")
        assert tool is not None
        assert tool.description is not None
        assert "semantically similar" in tool.description.lower()

    def test_search_collection_tool_has_description(self) -> None:
        """Test that search_collection tool has a description."""
        tool = mcp._tool_manager._tools.get("search_collection")
        assert tool is not None
        assert tool.description is not None
        assert "specific" in tool.description.lower()


class TestResourceRegistration:
    """Tests to verify resources are properly registered with FastMCP."""

    def test_collections_list_resource_registered(self) -> None:
        """Test that collections list resource is registered."""
        templates = mcp._resource_manager._templates
        assert "resource://collections/{_all}" in templates

    def test_collections_status_resource_registered(self) -> None:
        """Test that collections status resource is registered."""
        templates = mcp._resource_manager._templates
        assert "resource://collections/status/{_all}" in templates

    def test_collection_status_template_registered(self) -> None:
        """Test that collection status template is registered."""
        templates = mcp._resource_manager._templates
        assert "resource://collections/{name}" in templates

    def test_collections_list_resource_has_name(self) -> None:
        """Test that collections list resource has a name."""
        template = mcp._resource_manager._templates.get("resource://collections/{_all}")
        assert template is not None
        assert template.name == "CollectionsList"

    def test_collections_status_resource_has_name(self) -> None:
        """Test that collections status resource has a name."""
        template = mcp._resource_manager._templates.get(
            "resource://collections/status/{_all}"
        )
        assert template is not None
        assert template.name == "CollectionsStatusList"


class TestLifespan:
    """Tests for server lifespan context manager."""

    @patch.object(server_module, "_get_mcp_config")
    @patch.object(server_module, "_get_search_config")
    def test_lifespan_yields_config(self, mock_get_search, mock_get_mcp) -> None:
        """Test that lifespan yields configuration state."""
        from core.v1.config_models import MCPConfig, CoreV1SearchConfig

        mock_mcp_config = MCPConfig()
        mock_search_config = CoreV1SearchConfig()
        mock_get_mcp.return_value = mock_mcp_config
        mock_get_search.return_value = mock_search_config

        # Run lifespan as async context manager
        async def run_lifespan():
            async with lifespan(mcp) as state:
                return state

        result = run_async(run_lifespan())

        assert "mcp_config" in result
        assert "search_config" in result
        assert result["mcp_config"] == mock_mcp_config
        assert result["search_config"] == mock_search_config


class TestContextHandling:
    """Tests for context handling in tools and resources."""

    @patch.object(server_module, "svc_search")
    @patch.object(server_module, "get_search_config")
    def test_search_uses_lifespan_context_when_available(
        self, mock_get_config: MagicMock, mock_search: MagicMock
    ) -> None:
        """Test that search tool uses lifespan context when available."""
        from core.v1.config_models import CoreV1SearchConfig

        mock_config = CoreV1SearchConfig()
        mock_config.max_docs = 5
        mock_config.max_chunks = 3
        mock_config.score_threshold = 0.8
        mock_config.include_full_text = True
        mock_config.include_all_chunks = False
        mock_config.include_matched_chunks = True

        # Create a mock context with lifespan state
        mock_context = MagicMock()
        mock_fastmcp_context = MagicMock()
        mock_fastmcp_context.lifespan_context = {"search_config": mock_config}
        mock_context.fastmcp_context = mock_fastmcp_context

        mock_search.return_value = {"collection1": []}

        search_tool = mcp._tool_manager._tools.get("search")
        assert search_tool is not None
        search_tool.fn("test query", ctx=mock_context)

        # Should use config from lifespan context
        mock_search.assert_called_once()
        # get_search_config should not be called when context is available
        mock_get_config.assert_not_called()

    @patch.object(server_module, "svc_search")
    @patch.object(server_module, "get_search_config")
    def test_search_falls_back_to_getter_when_context_unavailable(
        self, mock_get_config: MagicMock, mock_search: MagicMock
    ) -> None:
        """Test that search falls back to getter when context unavailable."""
        from core.v1.config_models import CoreV1SearchConfig

        mock_config = CoreV1SearchConfig()
        mock_get_config.return_value = mock_config
        mock_search.return_value = {"collection1": []}

        search_tool = mcp._tool_manager._tools.get("search")
        assert search_tool is not None
        search_tool.fn("test query", ctx=None)

        mock_search.assert_called_once()
        mock_get_config.assert_called_once()

    @patch.object(server_module, "svc_status")
    @patch.object(server_module, "get_mcp_config")
    def test_collections_status_uses_lifespan_context(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        """Test that collections_status_list uses lifespan context."""
        from core.v1.config_models import MCPConfig

        mock_config = MCPConfig()
        mock_config.include_index_size = True

        mock_context = MagicMock()
        mock_fastmcp_context = MagicMock()
        mock_fastmcp_context.lifespan_context = {"mcp_config": mock_config}
        mock_context.fastmcp_context = mock_fastmcp_context

        mock_status_item = MagicMock()
        mock_status_item.name = "test_collection"
        mock_status_item.number_of_documents = 10
        mock_status_item.number_of_chunks = 50
        mock_status_item.updated_time = "2024-01-01T00:00:00"
        mock_status_item.last_modified_document_time = "2024-01-01T00:00:00"
        mock_status_item.indexers = ["default"]
        mock_status_item.index_size = 1024
        mock_status_item.source_type = "files"
        mock_status_item.relative_path = "./docs"
        mock_status_item.disk_size_bytes = 2048
        mock_status.return_value = [mock_status_item]

        template = mcp._resource_manager._templates.get(
            "resource://collections/status/{_all}"
        )
        assert template is not None
        run_async(template.fn(_all="all", ctx=mock_context))

        mock_status.assert_called_once_with(include_index_size=True)
        mock_get_config.assert_not_called()


class TestMainFunction:
    """Tests for main entry point."""

    @patch.object(server_module, "get_mcp_config")
    @patch.object(server_module, "mcp")
    @patch("indexed.mcp.server.argparse.ArgumentParser")
    def test_main_parses_arguments(
        self, mock_parser_class, mock_mcp, mock_get_config
    ) -> None:
        """Test that main function parses command line arguments."""
        from core.v1.config_models import MCPConfig

        mock_config = MCPConfig()
        mock_config.host = "0.0.0.0"
        mock_config.port = 8000
        mock_config.log_level = "INFO"
        mock_get_config.return_value = mock_config

        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.host = "127.0.0.1"
        mock_args.port = 9000
        mock_args.log_level = "DEBUG"
        mock_parser.parse_args.return_value = mock_args
        mock_parser_class.return_value = mock_parser

        server_module.main()

        mock_parser.add_argument.assert_any_call(
            "--host",
            default="0.0.0.0",
            help="Host to bind to (default: 0.0.0.0)",
        )
        mock_parser.add_argument.assert_any_call(
            "--port",
            type=int,
            default=8000,
            help="Port to bind to (default: 8000)",
        )
        mock_mcp.run.assert_called_once_with(
            host="127.0.0.1", port=9000, log_level="DEBUG"
        )

    @patch.object(server_module, "get_mcp_config")
    @patch.object(server_module, "mcp")
    @patch("indexed.mcp.server.argparse.ArgumentParser")
    def test_main_uses_config_defaults(
        self, mock_parser_class, mock_mcp, mock_get_config
    ) -> None:
        """Test that main function uses config defaults when args not provided."""
        from core.v1.config_models import MCPConfig

        mock_config = MCPConfig()
        mock_config.host = "localhost"
        mock_config.port = 8080
        mock_config.log_level = "WARNING"
        mock_get_config.return_value = mock_config

        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.host = "localhost"  # Same as default
        mock_args.port = 8080  # Same as default
        mock_args.log_level = "WARNING"  # Same as default
        mock_parser.parse_args.return_value = mock_args
        mock_parser_class.return_value = mock_parser

        server_module.main()

        mock_mcp.run.assert_called_once_with(
            host="localhost", port=8080, log_level="WARNING"
        )
