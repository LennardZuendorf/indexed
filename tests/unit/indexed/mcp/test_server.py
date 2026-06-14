"""Tests for the MCP server implementation.

Tools and resources route through the engine router getters
(``get_search_service`` / ``get_inspect_service``) and read engine + config
from lifespan state via the single ``get_lifespan_value`` helper. Tests patch
the router getters with mock service modules so they stay fast and never load
the heavy v1/v2 stacks, and they parametrize over both engines.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import indexed.mcp.resources as resources_module
import indexed.mcp.server as server_module
import indexed.mcp.tools as tools_module
from indexed.mcp.server import (
    _get_engine,
    _get_mcp_config,
    _get_search_config,
    lifespan,
    mcp,
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


def _ctx_with(**state):
    """Build a fake FastMCP Context carrying the given lifespan state."""
    return SimpleNamespace(lifespan_context=dict(state))


def _v1_search_config() -> object:
    from core.v1.config_models import CoreV1SearchConfig

    return CoreV1SearchConfig()


def _service_with(**attrs) -> MagicMock:
    """Return a mock service module exposing the given callables/attributes."""
    module = MagicMock()
    for name, value in attrs.items():
        setattr(module, name, value)
    return module


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


class TestGetEngine:
    """Tests for engine resolution in the server lifespan."""

    def test_get_engine_delegates_to_router(self) -> None:
        with patch(
            "indexed.services.engine_router.get_effective_engine",
            return_value="v1",
        ):
            assert _get_engine() == "v1"

    def test_get_engine_returns_router_v2(self) -> None:
        with patch(
            "indexed.services.engine_router.get_effective_engine",
            return_value="v2",
        ):
            assert _get_engine() == "v2"

    def test_get_engine_falls_back_to_v2_on_error(self) -> None:
        with patch(
            "indexed.services.engine_router.get_effective_engine",
            side_effect=Exception("router boom"),
        ):
            assert _get_engine() == "v2"


class TestSearchToolFunction:
    """Tests for the search tool underlying function, over both engines."""

    @pytest.mark.parametrize("engine", ["v1", "v2"])
    def test_search_returns_results(self, engine: str) -> None:
        canned = {
            "collection1": {
                "results": [
                    {
                        "id": "doc1",
                        "url": "file://doc1.md",
                        "matchedChunks": [
                            {
                                "chunkNumber": 0,
                                "score": 0.5,
                                "content": {"indexedData": "content one"},
                            }
                        ],
                    }
                ]
            },
        }
        mock_service = _service_with(search=MagicMock(return_value=canned))
        ctx = _ctx_with(engine=engine, search_config=_v1_search_config())

        search_tool = _get_tool("search")
        assert search_tool is not None

        if engine == "v2":
            with patch.object(tools_module, "_v2_search") as mock_v2:
                mock_v2.return_value = {"query": "q", "results": []}
                result = search_tool.fn("q", ctx=ctx)
            mock_v2.assert_called_once_with("q")
            assert result["query"] == "q"
        else:
            with patch.object(
                tools_module, "get_search_service", return_value=mock_service
            ):
                result = search_tool.fn("test query", ctx=ctx)
            mock_service.search.assert_called_once()
            assert result["query"] == "test query"
            assert result["total_collections_searched"] == 1
            assert result["total_chunks_found"] == 1

    def test_search_handles_indexed_error(self) -> None:
        from indexed_config.errors import IndexedError

        mock_service = _service_with(
            search=MagicMock(side_effect=IndexedError("Search failed"))
        )
        ctx = _ctx_with(engine="v1", search_config=_v1_search_config())

        search_tool = _get_tool("search")
        assert search_tool is not None
        with patch.object(
            tools_module, "get_search_service", return_value=mock_service
        ):
            result = search_tool.fn("test query", ctx=ctx)

        assert "error" in result
        assert "Search failed" in result["error"]

    def test_search_lets_unexpected_error_propagate(self) -> None:
        mock_service = _service_with(
            search=MagicMock(side_effect=RuntimeError("unexpected"))
        )
        ctx = _ctx_with(engine="v1", search_config=_v1_search_config())

        search_tool = _get_tool("search")
        assert search_tool is not None
        with patch.object(
            tools_module, "get_search_service", return_value=mock_service
        ):
            with pytest.raises(RuntimeError):
                search_tool.fn("test query", ctx=ctx)


class TestSearchCollectionToolFunction:
    """Tests for the search_collection tool underlying function, over both engines."""

    @pytest.mark.parametrize("engine", ["v1", "v2"])
    def test_search_collection_returns_results(self, engine: str) -> None:
        ctx = _ctx_with(engine=engine, search_config=_v1_search_config())
        search_collection_tool = _get_tool("search_collection")
        assert search_collection_tool is not None

        if engine == "v2":
            # Manifest detection returns None (no on-disk collection); resolves
            # to the lifespan engine default. Patch _v2_search to stay light.
            with (
                patch.object(
                    tools_module, "resolve_engine_for_collection", return_value="v2"
                ),
                patch.object(tools_module, "_v2_search") as mock_v2,
            ):
                mock_v2.return_value = {"query": "q", "results": []}
                result = search_collection_tool.fn("my_collection", "q", ctx=ctx)
            mock_v2.assert_called_once_with("q", collection="my_collection")
            assert result["query"] == "q"
        else:
            status_item = MagicMock()
            status_item.indexers = ["default_indexer"]
            inspect_service = _service_with(
                status=MagicMock(return_value=[status_item])
            )
            canned = {
                "my_collection": {
                    "results": [
                        {
                            "id": "doc1",
                            "url": "file://doc1.md",
                            "matchedChunks": [
                                {
                                    "chunkNumber": 0,
                                    "score": 0.5,
                                    "content": {"indexedData": "text"},
                                }
                            ],
                        }
                    ]
                }
            }
            search_service = _service_with(search=MagicMock(return_value=canned))
            with (
                patch.object(
                    tools_module, "resolve_engine_for_collection", return_value="v1"
                ),
                patch.object(
                    tools_module, "get_inspect_service", return_value=inspect_service
                ),
                patch.object(
                    tools_module, "get_search_service", return_value=search_service
                ),
            ):
                result = search_collection_tool.fn(
                    "my_collection", "test query", ctx=ctx
                )
            search_service.search.assert_called_once()
            assert result["query"] == "test query"
            assert result["results"][0]["collection"] == "my_collection"

    def test_search_collection_not_found_v1(self) -> None:
        inspect_service = _service_with(status=MagicMock(return_value=[]))
        ctx = _ctx_with(engine="v1", search_config=_v1_search_config())

        search_collection_tool = _get_tool("search_collection")
        assert search_collection_tool is not None
        with (
            patch.object(
                tools_module, "resolve_engine_for_collection", return_value="v1"
            ),
            patch.object(
                tools_module, "get_inspect_service", return_value=inspect_service
            ),
        ):
            result = search_collection_tool.fn("nonexistent", "test query", ctx=ctx)

        assert "error" in result
        assert "not found" in result["error"]

    def test_search_collection_handles_indexed_error(self) -> None:
        from indexed_config.errors import IndexedError

        status_item = MagicMock()
        status_item.indexers = ["default_indexer"]
        inspect_service = _service_with(status=MagicMock(return_value=[status_item]))
        search_service = _service_with(
            search=MagicMock(side_effect=IndexedError("Search failed"))
        )
        ctx = _ctx_with(engine="v1", search_config=_v1_search_config())

        search_collection_tool = _get_tool("search_collection")
        assert search_collection_tool is not None
        with (
            patch.object(
                tools_module, "resolve_engine_for_collection", return_value="v1"
            ),
            patch.object(
                tools_module, "get_inspect_service", return_value=inspect_service
            ),
            patch.object(
                tools_module, "get_search_service", return_value=search_service
            ),
        ):
            result = search_collection_tool.fn("my_collection", "test query", ctx=ctx)

        assert "error" in result


class TestV2SearchHelper:
    """Tests for the _v2_search routing helper."""

    def test_v2_search_routes_via_router_with_collections_dir(
        self, monkeypatch, tmp_path
    ) -> None:
        from core.v2.config import CoreV2EmbeddingConfig, CoreV2SearchConfig

        search_service = _service_with(
            search=MagicMock(return_value={"collectionName": "docs", "results": []})
        )
        monkeypatch.setattr(
            tools_module, "get_search_service", lambda engine: search_service
        )

        provider = MagicMock()
        provider.get.side_effect = lambda model: (
            CoreV2SearchConfig()
            if model is CoreV2SearchConfig
            else CoreV2EmbeddingConfig()
        )
        fake_service = MagicMock()
        fake_service.bind.return_value = provider
        monkeypatch.setattr(
            "indexed_config.ConfigService.instance", lambda: fake_service
        )
        monkeypatch.setattr("core.v2.config.register_config", lambda svc: None)
        monkeypatch.setattr(
            "indexed.utils.storage_info.resolve_preferred_collections_path",
            lambda: tmp_path,
        )

        result = tools_module._v2_search("query", collection="docs")

        assert "query" in result
        search_service.search.assert_called_once()
        _, kwargs = search_service.search.call_args
        # collections_dir must be threaded through so local storage works.
        assert kwargs["collections_dir"] == tmp_path
        # collection-scoped search builds a v2 SourceConfig (not a v1 import).
        assert kwargs["configs"][0].name == "docs"


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

    def test_read_collections_static(self) -> None:
        item = MagicMock()
        item.name = "alpha"
        inspect_service = _service_with(status=MagicMock(return_value=[item]))
        with patch.object(
            resources_module, "get_inspect_service", return_value=inspect_service
        ):
            result = _read_resource("resource://collections")

        assert result.contents
        assert "alpha" in result.contents[0].content

    def test_read_collections_status_static(self) -> None:
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
        inspect_service = _service_with(status=MagicMock(return_value=[item]))
        with patch.object(
            resources_module, "get_inspect_service", return_value=inspect_service
        ):
            result = _read_resource("resource://collections/status")

        assert result.contents
        assert "alpha" in result.contents[0].content

    def test_read_single_collection_template(self) -> None:
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
        inspect_service = _service_with(status=MagicMock(return_value=[item]))
        with (
            patch.object(
                resources_module, "get_inspect_service", return_value=inspect_service
            ),
            patch.object(
                resources_module, "resolve_engine_for_collection", return_value="v1"
            ),
        ):
            result = _read_resource("resource://collection/beta")

        assert result.contents
        assert "beta" in result.contents[0].content
        assert "number_of_documents" in result.contents[0].content


class TestLifespan:
    """Tests for server lifespan context manager."""

    @patch.object(server_module, "_get_engine")
    @patch.object(server_module, "_get_mcp_config")
    @patch.object(server_module, "_get_search_config")
    def test_lifespan_yields_config_and_engine(
        self, mock_get_search, mock_get_mcp, mock_get_engine
    ) -> None:
        from core.v1.config_models import CoreV1SearchConfig, MCPConfig

        mock_mcp_config = MCPConfig()
        mock_search_config = CoreV1SearchConfig()
        mock_get_mcp.return_value = mock_mcp_config
        mock_get_search.return_value = mock_search_config
        mock_get_engine.return_value = "v2"

        async def run_lifespan():
            async with lifespan(mcp) as state:
                return state

        result = run_async(run_lifespan())

        assert "mcp_config" in result
        assert "search_config" in result
        assert "engine" in result
        assert result["mcp_config"] == mock_mcp_config
        assert result["search_config"] == mock_search_config
        assert result["engine"] == "v2"


class TestContextHandling:
    """Tests for context/lifespan-state handling in tools and resources."""

    def test_search_reads_engine_and_config_from_lifespan(self) -> None:
        from core.v1.config_models import CoreV1SearchConfig

        cfg = CoreV1SearchConfig()
        ctx = _ctx_with(engine="v1", search_config=cfg)
        search_service = _service_with(search=MagicMock(return_value={"c": []}))

        search_tool = _get_tool("search")
        assert search_tool is not None
        with patch.object(
            tools_module, "get_search_service", return_value=search_service
        ):
            search_tool.fn("test query", ctx=ctx)

        search_service.search.assert_called_once()
        _, kwargs = search_service.search.call_args
        assert kwargs["max_docs"] == cfg.max_docs

    def test_search_defaults_to_v2_when_ctx_missing_engine(self) -> None:
        ctx = _ctx_with()  # empty lifespan state
        search_tool = _get_tool("search")
        assert search_tool is not None
        with patch.object(tools_module, "_v2_search") as mock_v2:
            mock_v2.return_value = {"query": "q", "results": []}
            search_tool.fn("q", ctx=ctx)
        mock_v2.assert_called_once()

    def test_get_lifespan_value_returns_lifespan_value(self) -> None:
        from indexed.mcp.config import get_lifespan_value

        ctx = _ctx_with(mcp_config="STORED")
        assert get_lifespan_value(ctx, "mcp_config", "DEFAULT") == "STORED"

    def test_get_lifespan_value_returns_default_when_key_missing(self) -> None:
        from indexed.mcp.config import get_lifespan_value

        ctx = _ctx_with()
        assert get_lifespan_value(ctx, "mcp_config", "DEFAULT") == "DEFAULT"

    def test_get_lifespan_value_returns_default_when_ctx_none(self) -> None:
        from indexed.mcp.config import get_lifespan_value

        assert get_lifespan_value(None, "mcp_config", "DEFAULT") == "DEFAULT"
