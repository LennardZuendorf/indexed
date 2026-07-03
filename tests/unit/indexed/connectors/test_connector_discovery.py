"""Tests for lazy connector discovery."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from indexed.connectors import _discover_connectors, _connector_classes


def test_discover_connectors_skips_packages_without_connector_module() -> None:
    module_info = MagicMock()
    module_info.ispkg = True
    module_info.name = "connectors.fakepkg"

    with (
        patch("indexed.connectors.pkgutil.iter_modules", return_value=[module_info]),
        patch("indexed.connectors.importlib.import_module", side_effect=ImportError),
    ):
        assert _discover_connectors() == []


def test_discover_connectors_collects_classes_with_meta() -> None:
    meta = SimpleNamespace(name="demo")

    class DemoConnector:
        META = meta
        __module__ = "connectors.demo.connector"

    module = MagicMock()
    module.__name__ = "connectors.demo.connector"
    module.DemoConnector = DemoConnector

    module_info = MagicMock()
    module_info.ispkg = True
    module_info.name = "connectors.demo"

    with (
        patch("indexed.connectors.pkgutil.iter_modules", return_value=[module_info]),
        patch("indexed.connectors.importlib.import_module", return_value=module),
        patch(
            "indexed.connectors.inspect.getmembers",
            return_value=[("DemoConnector", DemoConnector)],
        ),
        patch("indexed.connectors.inspect.isclass", return_value=True),
    ):
        discovered = _discover_connectors()

    assert DemoConnector in discovered


def test_connector_classes_lazy_loads_once() -> None:
    sentinel = [MagicMock(META=SimpleNamespace(name="x"))]
    with patch(
        "indexed.connectors._discover_connectors", return_value=sentinel
    ) as mock:
        import indexed.connectors as mod

        mod.CONNECTORS = mod._UNDISCOVERED
        first = _connector_classes()
        second = _connector_classes()
        assert first is second
        mock.assert_called_once()
