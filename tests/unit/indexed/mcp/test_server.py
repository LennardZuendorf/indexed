"""Tests for the MCP server implementation."""

import asyncio
from unittest.mock import patch, MagicMock

import pytest

# Import the server module to access the underlying functions
import indexed.mcp.server as server_module
import indexed.mcp.tools as tools_module
import indexed.mcp.resources as resources_module
from indexed.mcp.server import (
    mcp,
    _get_mcp_config,
    _get_search_config,
    lifespan,
)


def run_async(coro_or_result):
    """Run coroutine synchronously or return result directly if not a coroutine."""
    if asyncio.iscoroutine(coro_or_result):
        return asyncio.run(coro_or_result)
    return coro_or_result


def _get_tool(name: str):
    """Fetch a registered tool by name via FastMCP v3 public API."""
    return asyncio.run(mcp.get_tool(name))


def _get_resource(uri: str):
    """Fetch a static resource by URI via FastMCP v3 public API."""
    return asyncio.run(mcp.get_resource(uri))


def _get_template(uri: str):
    """Fetch a parameterised resource template by URI via FastMCP v3 public API."""
    return asyncio.run(mcp.get_resource_template(uri))


def _list_resource_uris() -> list[str]:
    """Return URIs of static resources registered on the server."""
    resources = asyncio.run(mcp.list_resources())
    return [str(r.uri) for r in resources]


def _list_template_uris() -> list[str]:
    """Return URI templates registered on the server."""
    templates = asyncio.run(mcp.list_resource_templates())
    return [t.uri_template for t in templates]


def _list_tool_names() -> list[str]:
    """Return names of registered tools."""
    tools = asyncio.run(mcp.list_tools())
    return [t.name for t in tools]


def _read_resource(uri: str):
    """Dispatch a resource read through FastMCP's full URI resolution."""
    return asyncio.run(mcp.read_resource(uri))


@pytest.fixture(autouse=True)
def mock_fastmcp_context():
    """Provide a minimal FastMCP Context via contextvar for dependency injection."""
    try:
        from fastmcp.server.context import _current_context, Context

        dummy_server = MagicMock()
        ctx = Context(dummy_server)
        token = _current_context.set(ctx)
        yield ctx
        _current_context.reset(token)
    except Exception:
        yield None


class TestServerInstance:
    """Tests for the FastMCP server instance."""

    def test_server_has_name(self) -> None:
        assert mcp.name == "Indexed MCP Server"

    def test_server_has_lifespan(self) -> None:
        assert mcp._lifespan is not None

    def test_server_has_middleware(self) -> None:
        assert hasattr(mcp, "middleware")


class TestConfigLoading:
    """Tests for configuration loading functions."""

    def test_get_mcp_config_returns_config(self) -> None:
        from core.v1.config_models import MCPConfig

        config = _get_mcp_config()
        assert isinstance(config, MCPConfig)

    def test_get_search_config_returns_config(self) -> None:
        from core.v1.config_models import CoreV1SearchConfig

        config = _get_search_config()
        assert isinstance(config, CoreV1SearchConfig)

    def test_get_mcp_config_fallback_on_error(self) -> None:
        from core.v1.config_models import MCPConfig

        with patch.object(server_module, "ConfigService") as mock_config:
            mock_config.instance.side_effect = Exception("Config error")
            config = _get_mcp_config()
            assert isinstance(config, MCPConfig)

    def test_get_search_config_fallback_on_error(self) -> None:
        from core.v1.config_models import CoreV1SearchConfig

        with patch.object(server_module, "ConfigService") as mock_config:
            mock_config.instance.side_effect = Exception("Config error")
            config = _get_search_config()
            assert isinstance(config, CoreV1SearchConfig)


class TestSearchToolFunction:
    """Tests for the search tool underlying function."""

    @patch.object(tools_module, "svc_search")
    @patch.object(server_module, "_get_search_config")
    def test_search_returns_results(
        self, mock_get_config: MagicMock, mock_search: MagicMock
    ) -> None:
        mock_config = MagicMock()
        mock_config.max_docs = 10
        mock_config.max_chunks = 5
        mock_config.score_threshold = 0.7
        mock_config.include_full_text = False
        mock_config.include_all_chunks = False
        mock_config.include_matched_chunks = True
        mock_get_config.return_value = mock_config

        mock_search.return_value = {
            "collection1": {
                "results": [
                    {
                        "id": "doc1",
                        "url": "file://doc1.md",
                        "matchedChunks": [
                            {
                                "chunkNumber": 0,
                                "score": 0.5,
                                "content": {
                                    "indexedData": "test content from collection1"
                                },
                            }
                        ],
                    }
                ]
            },
            "collection2": {
                "results": [
                    {
                        "id": "doc2",
                        "url": "file://doc2.md",
                        "matchedChunks": [
                            {
                                "chunkNumber": 0,
                                "score": 0.6,
                                "content": {
                                    "indexedData": "test content from collection2"
                                },
                            }
                        ],
                    }
                ]
            },
        }

        search_tool = _get_tool("search")
        assert search_tool is not None
        result = search_tool.fn("test query")

        assert result["query"] == "test query"
        assert result["total_collections_searched"] == 2
        assert result["total_documents_found"] == 2
        assert result["total_chunks_found"] == 2
        assert len(result["results"]) == 2
        collections_in_results = {r["collection"] for r in result["results"]}
        assert "collection1" in collections_in_results
        assert "collection2" in collections_in_results
        mock_search.assert_called_once()

    @patch.object(tools_module, "svc_search")
    @patch.object(server_module, "_get_search_config")
    def test_search_handles_error(
        self, mock_get_config: MagicMock, mock_search: MagicMock
    ) -> None:
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        mock_search.side_effect = Exception("Search failed")

        search_tool = _get_tool("search")
        assert search_tool is not None
        result = search_tool.fn("test query")

        assert "error" in result
        assert "Search failed" in result["error"]


class TestSearchCollectionToolFunction:
    """Tests for the search_collection tool underlying function."""

    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "svc_status")
    @patch.object(server_module, "_get_search_config")
    def test_search_collection_returns_results(
        self,
        mock_get_config: MagicMock,
        mock_status: MagicMock,
        mock_search: MagicMock,
    ) -> None:
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

        mock_search.return_value = {
            "my_collection": {
                "results": [
                    {
                        "id": "doc1",
                        "url": "file://doc1.md",
                        "matchedChunks": [
                            {
                                "chunkNumber": 0,
                                "score": 0.5,
                                "content": {"indexedData": "test content"},
                            }
                        ],
                    }
                ]
            }
        }

        search_collection_tool = _get_tool("search_collection")
        assert search_collection_tool is not None
        result = search_collection_tool.fn("my_collection", "test query")

        assert result["query"] == "test query"
        assert result["total_collections_searched"] == 1
        assert result["total_documents_found"] == 1
        assert result["total_chunks_found"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["collection"] == "my_collection"
        mock_search.assert_called_once()

    @patch.object(tools_module, "svc_status")
    @patch.object(server_module, "_get_search_config")
    def test_search_collection_not_found(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        mock_status.return_value = []

        search_collection_tool = _get_tool("search_collection")
        assert search_collection_tool is not None
        result = search_collection_tool.fn("nonexistent", "test query")

        assert "error" in result
        assert "not found" in result["error"]

    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "svc_status")
    @patch.object(server_module, "_get_search_config")
    def test_search_collection_handles_error(
        self,
        mock_get_config: MagicMock,
        mock_status: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config

        mock_status_item = MagicMock()
        mock_status_item.indexers = ["default_indexer"]
        mock_status.return_value = [mock_status_item]

        mock_search.side_effect = Exception("Search failed")

        search_collection_tool = _get_tool("search_collection")
        assert search_collection_tool is not None
        result = search_collection_tool.fn("my_collection", "test query")

        assert "error" in result


class TestCollectionsListResourceFunction:
    """Tests for the collections_list resource underlying function."""

    @patch.object(resources_module, "svc_status")
    def test_collections_list_returns_names(self, mock_status: MagicMock) -> None:
        mock_status1 = MagicMock()
        mock_status1.name = "collection1"
        mock_status2 = MagicMock()
        mock_status2.name = "collection2"
        mock_status.return_value = [mock_status1, mock_status2]

        resource = _get_resource("resource://collections")
        assert resource is not None
        result = run_async(resource.fn())

        assert result == {"collections": ["collection1", "collection2"]}

    @patch.object(resources_module, "svc_status")
    def test_collections_list_handles_error(self, mock_status: MagicMock) -> None:
        mock_status.side_effect = Exception("Status failed")

        resource = _get_resource("resource://collections")
        assert resource is not None
        result = run_async(resource.fn())

        assert "error" in result
        assert "Status failed" in result["error"]


class TestCollectionsStatusListResourceFunction:
    """Tests for the collections_status_list resource underlying function."""

    @patch.object(resources_module, "svc_status")
    @patch.object(server_module, "_get_mcp_config")
    def test_collections_status_list_returns_details(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
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

        resource = _get_resource("resource://collections/status")
        assert resource is not None
        result = run_async(resource.fn())

        collections = result["collections"]
        assert len(collections) == 1
        assert collections[0]["name"] == "collection1"
        assert collections[0]["number_of_documents"] == 100
        assert collections[0]["number_of_chunks"] == 500

    @patch.object(resources_module, "svc_status")
    @patch.object(server_module, "_get_mcp_config")
    def test_collections_status_list_handles_error(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        mock_status.side_effect = Exception("Status failed")

        resource = _get_resource("resource://collections/status")
        assert resource is not None
        result = run_async(resource.fn())

        assert "error" in result
        assert "Status failed" in result["error"]


class TestCollectionStatusResourceTemplateFunction:
    """Tests for the collection_status resource template underlying function."""

    @patch.object(resources_module, "svc_status")
    @patch.object(server_module, "_get_mcp_config")
    def test_collection_status_returns_details(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
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

        template = _get_template("resource://collection/{name}")
        assert template is not None
        result = run_async(template.fn(name="my_collection"))

        assert result["name"] == "my_collection"
        assert result["number_of_documents"] == 50

    @patch.object(resources_module, "svc_status")
    @patch.object(server_module, "_get_mcp_config")
    def test_collection_status_not_found(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        mock_status.return_value = []

        template = _get_template("resource://collection/{name}")
        assert template is not None
        result = run_async(template.fn(name="nonexistent"))

        assert "error" in result
        assert "not found" in result["error"]

    @patch.object(resources_module, "svc_status")
    @patch.object(server_module, "_get_mcp_config")
    def test_collection_status_handles_error(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        mock_config = MagicMock()
        mock_get_config.return_value = mock_config
        mock_status.side_effect = Exception("Status failed")

        template = _get_template("resource://collection/{name}")
        assert template is not None
        result = run_async(template.fn(name="my_collection"))

        assert "error" in result


class TestToolRegistration:
    """Tests to verify tools are properly registered with FastMCP."""

    def test_search_tool_registered(self) -> None:
        assert "search" in _list_tool_names()

    def test_search_collection_tool_registered(self) -> None:
        assert "search_collection" in _list_tool_names()

    def test_search_tool_has_description(self) -> None:
        tool = _get_tool("search")
        assert tool is not None
        assert tool.description is not None
        assert "semantically similar" in tool.description.lower()

    def test_search_collection_tool_has_description(self) -> None:
        tool = _get_tool("search_collection")
        assert tool is not None
        assert tool.description is not None
        assert "specific" in tool.description.lower()


class TestResourceRegistration:
    """Tests to verify resources are properly registered with FastMCP."""

    def test_collections_list_resource_registered(self) -> None:
        assert "resource://collections" in _list_resource_uris()

    def test_collections_status_resource_registered(self) -> None:
        assert "resource://collections/status" in _list_resource_uris()

    def test_collection_status_template_registered(self) -> None:
        assert "resource://collection/{name}" in _list_template_uris()

    def test_collections_list_resource_has_name(self) -> None:
        resource = _get_resource("resource://collections")
        assert resource is not None
        assert resource.name == "CollectionsList"

    def test_collections_status_resource_has_name(self) -> None:
        resource = _get_resource("resource://collections/status")
        assert resource is not None
        assert resource.name == "CollectionsStatusList"


class TestResourceDispatch:
    """End-to-end resource dispatch tests via mcp.read_resource()."""

    @patch.object(resources_module, "svc_status")
    def test_read_collections_static(self, mock_status: MagicMock) -> None:
        item = MagicMock()
        item.name = "alpha"
        mock_status.return_value = [item]

        result = _read_resource("resource://collections")

        assert result.contents
        assert "alpha" in result.contents[0].content

    @patch.object(resources_module, "svc_status")
    @patch.object(server_module, "_get_mcp_config")
    def test_read_collections_status_static(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        from core.v1.config_models import MCPConfig

        mock_get_config.return_value = MCPConfig()
        item = MagicMock()
        item.name = "alpha"
        item.number_of_documents = 1
        item.number_of_chunks = 2
        item.updated_time = None
        item.last_modified_document_time = None
        item.indexers = []
        item.index_size = 0
        item.source_type = "files"
        item.relative_path = None
        item.disk_size_bytes = 0
        mock_status.return_value = [item]

        result = _read_resource("resource://collections/status")

        assert result.contents
        assert "alpha" in result.contents[0].content

    @patch.object(resources_module, "svc_status")
    @patch.object(server_module, "_get_mcp_config")
    def test_read_single_collection_template(
        self, mock_get_config: MagicMock, mock_status: MagicMock
    ) -> None:
        from core.v1.config_models import MCPConfig

        mock_get_config.return_value = MCPConfig()
        item = MagicMock()
        item.name = "beta"
        item.number_of_documents = 3
        item.number_of_chunks = 9
        item.updated_time = None
        item.last_modified_document_time = None
        item.indexers = []
        item.index_size = 0
        item.source_type = "files"
        item.relative_path = None
        item.disk_size_bytes = 0
        mock_status.return_value = [item]

        result = _read_resource("resource://collection/beta")

        assert result.contents
        assert "beta" in result.contents[0].content
        assert "number_of_documents" in result.contents[0].content


class TestLifespan:
    """Tests for server lifespan context manager."""

    @patch.object(server_module, "_get_mcp_config")
    @patch.object(server_module, "_get_search_config")
    def test_lifespan_yields_config(self, mock_get_search, mock_get_mcp) -> None:
        from core.v1.config_models import MCPConfig, CoreV1SearchConfig

        mock_mcp_config = MCPConfig()
        mock_search_config = CoreV1SearchConfig()
        mock_get_mcp.return_value = mock_mcp_config
        mock_get_search.return_value = mock_search_config

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

    @patch.object(tools_module, "svc_search")
    @patch.object(server_module, "_get_search_config")
    def test_search_uses_lifespan_context_when_available(
        self, mock_get_config: MagicMock, mock_search: MagicMock
    ) -> None:
        from core.v1.config_models import CoreV1SearchConfig

        mock_config = CoreV1SearchConfig()
        mock_config.max_docs = 5
        mock_config.max_chunks = 3
        mock_config.score_threshold = 0.8
        mock_config.include_full_text = True
        mock_config.include_all_chunks = False
        mock_config.include_matched_chunks = True

        mock_context = MagicMock()
        mock_context.lifespan_context = {"search_config": mock_config}

        mock_search.return_value = {"collection1": []}

        search_tool = _get_tool("search")
        assert search_tool is not None
        search_tool.fn("test query", ctx=mock_context)

        mock_search.assert_called_once()
        mock_get_config.assert_not_called()

    @patch.object(tools_module, "svc_search")
    @patch.object(tools_module, "_resolve_config")
    def test_search_falls_back_to_getter_when_context_unavailable(
        self, mock_resolve_config: MagicMock, mock_search: MagicMock
    ) -> None:
        from core.v1.config_models import CoreV1SearchConfig

        mock_config = CoreV1SearchConfig()
        mock_resolve_config.return_value = mock_config
        mock_search.return_value = {"collection1": []}

        search_tool = _get_tool("search")
        assert search_tool is not None
        search_tool.fn("test query", ctx=None)

        mock_search.assert_called_once()
        assert mock_resolve_config.call_count >= 1

    def test_resolve_config_returns_lifespan_value(self) -> None:
        """Direct test: resolve_config returns the lifespan-stored config when present."""
        from indexed.mcp.config import resolve_config
        from core.v1.config_models import MCPConfig

        cfg = MCPConfig()
        ctx = MagicMock()
        ctx.lifespan_context = {"mcp_config": cfg}
        loader = MagicMock()

        result = resolve_config(ctx, "mcp_config", loader)

        assert result is cfg
        loader.assert_not_called()

    def test_resolve_config_falls_back_to_loader_when_key_missing(self) -> None:
        """Direct test: resolve_config calls loader when ctx has no matching key."""
        from indexed.mcp.config import resolve_config
        from core.v1.config_models import MCPConfig

        cfg = MCPConfig()
        ctx = MagicMock()
        ctx.lifespan_context = {}
        loader = MagicMock(return_value=cfg)

        result = resolve_config(ctx, "mcp_config", loader)

        assert result is cfg
        loader.assert_called_once()

    def test_resolve_config_falls_back_to_loader_when_ctx_none(self) -> None:
        """Direct test: resolve_config calls loader when ctx is None."""
        from indexed.mcp.config import resolve_config
        from core.v1.config_models import MCPConfig

        cfg = MCPConfig()
        loader = MagicMock(return_value=cfg)

        result = resolve_config(None, "mcp_config", loader)

        assert result is cfg
        loader.assert_called_once()
