"""Tests for the MCP server implementation."""

from unittest.mock import patch, MagicMock

# Import the server module to access the underlying functions
import indexed.mcp.server as server_module
from indexed.mcp.server import (
    mcp,
    get_mcp_config,
    get_search_config,
    _get_mcp_config,
    _get_search_config,
)


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

        resource = mcp._resource_manager._resources.get("resource://collections")
        assert resource is not None
        result = resource.fn()

        assert result == ["collection1", "collection2"]

    @patch.object(server_module, "svc_status")
    def test_collections_list_handles_error(self, mock_status: MagicMock) -> None:
        """Test that collections_list handles errors gracefully."""
        mock_status.side_effect = Exception("Status failed")

        resource = mcp._resource_manager._resources.get("resource://collections")
        assert resource is not None
        result = resource.fn()

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

        resource = mcp._resource_manager._resources.get("resource://collections/status")
        assert resource is not None
        result = resource.fn()

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

        resource = mcp._resource_manager._resources.get("resource://collections/status")
        assert resource is not None
        result = resource.fn()

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
        result = template.fn("my_collection")

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
        result = template.fn("nonexistent")

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
        result = template.fn("my_collection")

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
        assert "semantic similarity" in tool.description.lower()

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
        resources = mcp._resource_manager._resources
        assert "resource://collections" in resources

    def test_collections_status_resource_registered(self) -> None:
        """Test that collections status resource is registered."""
        resources = mcp._resource_manager._resources
        assert "resource://collections/status" in resources

    def test_collection_status_template_registered(self) -> None:
        """Test that collection status template is registered."""
        templates = mcp._resource_manager._templates
        assert "resource://collections/{name}" in templates

    def test_collections_list_resource_has_name(self) -> None:
        """Test that collections list resource has a name."""
        resource = mcp._resource_manager._resources.get("resource://collections")
        assert resource is not None
        assert resource.name == "CollectionsList"

    def test_collections_status_resource_has_name(self) -> None:
        """Test that collections status resource has a name."""
        resource = mcp._resource_manager._resources.get("resource://collections/status")
        assert resource is not None
        assert resource.name == "CollectionsStatusList"
