"""Tests for MCP resource implementations.

Resources route through the engine router (``get_inspect_service``) and read
engine + config from lifespan state via ``get_lifespan_value``. FastMCP excludes
the injected ``Context`` from a resource's validated signature, so these tests
do NOT pass ``ctx`` to ``.fn``; instead they patch ``get_lifespan_value`` on the
module to inject engine/config, and call the module-level ``_status_for_engine``
seam directly for pure routing assertions. The router getter is patched with a
mock service module so the heavy v1/v2 stacks never load.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import indexed.mcp.resources as resources_module


def run_async(value):
    """Await a coroutine if needed, else return the value directly."""
    if asyncio.iscoroutine(value):
        return asyncio.run(value)
    return value


def _lifespan_getter(engine="v2", mcp_config=None):
    """Build a get_lifespan_value replacement injecting engine + mcp_config."""

    def _get(ctx, key, default):
        store = {"engine": engine, "mcp_config": mcp_config or default}
        return store.get(key, default)

    return _get


def _service_with(**attrs) -> MagicMock:
    module = MagicMock()
    for name, value in attrs.items():
        setattr(module, name, value)
    return module


def _status_item(name: str) -> MagicMock:
    item = MagicMock()
    item.name = name
    item.number_of_documents = 10
    item.number_of_chunks = 50
    item.updated_time = "2024-01-01T00:00:00"
    item.last_modified_document_time = "2024-01-01T00:00:00"
    item.indexers = ["indexer1"]
    item.index_size = 1024
    item.source_type = "files"
    item.relative_path = "./docs"
    item.disk_size_bytes = 2048
    return item


def _get_resource_fn(name: str):
    from indexed.mcp.server import mcp

    return asyncio.run(mcp.get_resource(name)).fn


def _get_template_fn(uri: str):
    from indexed.mcp.server import mcp

    return asyncio.run(mcp.get_resource_template(uri)).fn


class TestStatusForEngineRouting:
    """The module-level _status_for_engine seam routes through the router."""

    def test_v2_passes_collections_dir(self, monkeypatch, tmp_path) -> None:
        inspect_service = _service_with(status=MagicMock(return_value=[]))
        monkeypatch.setattr(
            "indexed.utils.storage_info.resolve_preferred_collections_path",
            lambda: tmp_path,
        )
        with patch.object(
            resources_module, "get_inspect_service", return_value=inspect_service
        ) as mock_getter:
            resources_module._status_for_engine("v2", None, include_index_size=False)

        mock_getter.assert_called_once_with("v2")
        _, kwargs = inspect_service.status.call_args
        assert kwargs["collections_dir"] == tmp_path

    def test_v1_passes_include_index_size(self) -> None:
        inspect_service = _service_with(status=MagicMock(return_value=[]))
        with patch.object(
            resources_module, "get_inspect_service", return_value=inspect_service
        ) as mock_getter:
            resources_module._status_for_engine("v1", None, include_index_size=True)

        mock_getter.assert_called_once_with("v1")
        _, kwargs = inspect_service.status.call_args
        assert kwargs["include_index_size"] is True

    def test_v1_named_collection_positional(self) -> None:
        inspect_service = _service_with(status=MagicMock(return_value=[]))
        with patch.object(
            resources_module, "get_inspect_service", return_value=inspect_service
        ):
            resources_module._status_for_engine(
                "v1", ["docs"], include_index_size=False
            )

        args, kwargs = inspect_service.status.call_args
        assert args[0] == ["docs"]
        assert kwargs["include_index_size"] is False


class TestCollectionsList:
    """resource://collections — list collection names, over both engines."""

    @pytest.mark.parametrize("engine", ["v1", "v2"])
    def test_returns_names(self, engine: str, monkeypatch, tmp_path) -> None:
        inspect_service = _service_with(
            status=MagicMock(return_value=[_status_item("a"), _status_item("b")])
        )
        monkeypatch.setattr(
            "indexed.utils.storage_info.resolve_preferred_collections_path",
            lambda: tmp_path,
        )
        fn = _get_resource_fn("resource://collections")
        with (
            patch.object(
                resources_module, "get_lifespan_value", _lifespan_getter(engine=engine)
            ),
            patch.object(
                resources_module, "get_inspect_service", return_value=inspect_service
            ),
        ):
            result = run_async(fn())

        assert result == {"collections": ["a", "b"]}

    def test_handles_indexed_error(self, monkeypatch, tmp_path) -> None:
        from indexed_config.errors import IndexedError

        inspect_service = _service_with(
            status=MagicMock(side_effect=IndexedError("boom"))
        )
        monkeypatch.setattr(
            "indexed.utils.storage_info.resolve_preferred_collections_path",
            lambda: tmp_path,
        )
        fn = _get_resource_fn("resource://collections")
        with (
            patch.object(
                resources_module, "get_lifespan_value", _lifespan_getter(engine="v2")
            ),
            patch.object(
                resources_module, "get_inspect_service", return_value=inspect_service
            ),
        ):
            result = run_async(fn())

        assert "error" in result
        assert "boom" in result["error"]

    def test_lets_unexpected_error_propagate(self, monkeypatch, tmp_path) -> None:
        inspect_service = _service_with(
            status=MagicMock(side_effect=RuntimeError("unexpected"))
        )
        monkeypatch.setattr(
            "indexed.utils.storage_info.resolve_preferred_collections_path",
            lambda: tmp_path,
        )
        fn = _get_resource_fn("resource://collections")
        with (
            patch.object(
                resources_module, "get_lifespan_value", _lifespan_getter(engine="v2")
            ),
            patch.object(
                resources_module, "get_inspect_service", return_value=inspect_service
            ),
        ):
            with pytest.raises(RuntimeError):
                run_async(fn())


class TestCollectionsStatusList:
    """resource://collections/status — detailed status, over both engines."""

    @pytest.mark.parametrize("engine", ["v1", "v2"])
    def test_returns_details(self, engine: str, monkeypatch, tmp_path) -> None:
        from core.v1.config_models import MCPConfig

        inspect_service = _service_with(
            status=MagicMock(return_value=[_status_item("alpha")])
        )
        monkeypatch.setattr(
            "indexed.utils.storage_info.resolve_preferred_collections_path",
            lambda: tmp_path,
        )
        fn = _get_resource_fn("resource://collections/status")
        with (
            patch.object(
                resources_module,
                "get_lifespan_value",
                _lifespan_getter(engine=engine, mcp_config=MCPConfig()),
            ),
            patch.object(
                resources_module, "get_inspect_service", return_value=inspect_service
            ),
        ):
            result = run_async(fn())

        collections = result["collections"]
        assert len(collections) == 1
        assert collections[0]["name"] == "alpha"
        assert collections[0]["number_of_documents"] == 10


class TestCollectionStatus:
    """resource://collection/{name} — status for a single collection."""

    @pytest.mark.parametrize("engine", ["v1", "v2"])
    def test_returns_details(self, engine: str, monkeypatch, tmp_path) -> None:
        from core.v1.config_models import MCPConfig

        inspect_service = _service_with(
            status=MagicMock(return_value=[_status_item("my_collection")])
        )
        monkeypatch.setattr(
            "indexed.utils.storage_info.resolve_preferred_collections_path",
            lambda: tmp_path,
        )
        fn = _get_template_fn("resource://collection/{name}")
        with (
            patch.object(
                resources_module,
                "get_lifespan_value",
                _lifespan_getter(engine=engine, mcp_config=MCPConfig()),
            ),
            patch.object(
                resources_module, "get_inspect_service", return_value=inspect_service
            ),
            patch.object(
                resources_module, "resolve_engine_for_collection", return_value=engine
            ),
        ):
            result = run_async(fn(name="my_collection"))

        assert result["name"] == "my_collection"
        assert result["number_of_documents"] == 10

    def test_not_found(self, monkeypatch, tmp_path) -> None:
        from core.v1.config_models import MCPConfig

        inspect_service = _service_with(status=MagicMock(return_value=[]))
        monkeypatch.setattr(
            "indexed.utils.storage_info.resolve_preferred_collections_path",
            lambda: tmp_path,
        )
        fn = _get_template_fn("resource://collection/{name}")
        with (
            patch.object(
                resources_module,
                "get_lifespan_value",
                _lifespan_getter(engine="v1", mcp_config=MCPConfig()),
            ),
            patch.object(
                resources_module, "get_inspect_service", return_value=inspect_service
            ),
            patch.object(
                resources_module, "resolve_engine_for_collection", return_value="v1"
            ),
        ):
            result = run_async(fn(name="nonexistent"))

        assert "error" in result
        assert "not found" in result["error"]

    def test_handles_indexed_error(self, monkeypatch, tmp_path) -> None:
        from core.v1.config_models import MCPConfig
        from indexed_config.errors import IndexedError

        inspect_service = _service_with(
            status=MagicMock(side_effect=IndexedError("status boom"))
        )
        monkeypatch.setattr(
            "indexed.utils.storage_info.resolve_preferred_collections_path",
            lambda: tmp_path,
        )
        fn = _get_template_fn("resource://collection/{name}")
        with (
            patch.object(
                resources_module,
                "get_lifespan_value",
                _lifespan_getter(engine="v1", mcp_config=MCPConfig()),
            ),
            patch.object(
                resources_module, "get_inspect_service", return_value=inspect_service
            ),
            patch.object(
                resources_module, "resolve_engine_for_collection", return_value="v1"
            ),
        ):
            result = run_async(fn(name="my_collection"))

        assert "error" in result
        assert "status boom" in result["error"]
