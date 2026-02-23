"""Tests for connector registry compatibility validation and lookups."""

import sys
import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


from indexed.connectors import (
    validate_connector_compatibility,
    get_connector_registry,
    list_connector_names,
    check_all_connectors_compatibility,
)


def _make_connector(name: str, min_core_version: str | None = None):
    """Create a minimal connector class with a META attribute."""
    meta = SimpleNamespace(name=name, min_core_version=min_core_version)

    class FakeConnector:
        META = meta

    FakeConnector.__name__ = f"{name.capitalize()}Connector"
    return FakeConnector


def _core_mock(version: str) -> MagicMock:
    m = MagicMock()
    m.__version__ = version
    return m


class TestValidateConnectorCompatibility:
    """validate_connector_compatibility returns (bool, str)."""

    def test_no_min_version_is_always_compatible(self):
        cls = _make_connector("files", min_core_version=None)
        with patch.dict(sys.modules, {"core.v1": _core_mock("1.0.0")}):
            is_compat, msg = validate_connector_compatibility(cls)
        assert is_compat is True
        assert msg == ""

    def test_compatible_version_returns_true_empty_message(self):
        cls = _make_connector("files", min_core_version="1.0.0")
        with patch.dict(sys.modules, {"core.v1": _core_mock("2.0.0")}):
            is_compat, msg = validate_connector_compatibility(cls)
        assert is_compat is True
        assert msg == ""

    def test_exact_version_match_is_compatible(self):
        cls = _make_connector("conn", min_core_version="1.5.0")
        with patch.dict(sys.modules, {"core.v1": _core_mock("1.5.0")}):
            is_compat, msg = validate_connector_compatibility(cls)
        assert is_compat is True

    def test_older_core_returns_false_with_error_message(self):
        cls = _make_connector("myconn", min_core_version="99.0.0")
        with patch.dict(sys.modules, {"core.v1": _core_mock("1.0.0")}):
            is_compat, msg = validate_connector_compatibility(cls)
        assert is_compat is False
        assert "myconn" in msg
        assert len(msg) > 0

    def test_unparseable_version_returns_compatible_with_warning(self):
        cls = _make_connector("myconn", min_core_version="not-semver")
        with patch.dict(sys.modules, {"core.v1": _core_mock("also-not-semver")}):
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                is_compat, _ = validate_connector_compatibility(cls)
        assert is_compat is True


class TestGetConnectorRegistry:
    """get_connector_registry returns {name: class} for compatible connectors."""

    @patch("indexed.connectors.CONNECTORS", [])
    def test_no_connectors_returns_empty_dict(self):
        assert get_connector_registry() == {}

    def test_compatible_connector_appears_in_registry(self):
        cls = _make_connector("files", min_core_version=None)
        with patch.dict(sys.modules, {"core.v1": _core_mock("2.0.0")}):
            with patch("indexed.connectors.CONNECTORS", [cls]):
                registry = get_connector_registry()
        assert "files" in registry

    def test_incompatible_connector_not_in_registry(self):
        cls = _make_connector("old", min_core_version="99.0.0")
        with patch.dict(sys.modules, {"core.v1": _core_mock("1.0.0")}):
            with patch("indexed.connectors.CONNECTORS", [cls]):
                with warnings.catch_warnings(record=True):
                    warnings.simplefilter("always")
                    registry = get_connector_registry()
        assert "old" not in registry

    def test_connector_without_meta_not_in_registry(self):
        class NoMeta:
            pass

        with patch("indexed.connectors.CONNECTORS", [NoMeta]):
            registry = get_connector_registry()
        assert len(registry) == 0

    def test_multiple_compatible_connectors_all_appear(self):
        cls1 = _make_connector("files")
        cls2 = _make_connector("jira", min_core_version="1.0.0")
        with patch.dict(sys.modules, {"core.v1": _core_mock("2.0.0")}):
            with patch("indexed.connectors.CONNECTORS", [cls1, cls2]):
                registry = get_connector_registry()
        assert "files" in registry
        assert "jira" in registry


class TestListConnectorNames:
    """list_connector_names returns a list of name strings."""

    @patch("indexed.connectors.CONNECTORS", [])
    def test_no_connectors_returns_empty_list(self):
        assert list_connector_names() == []

    def test_returns_name_strings(self):
        cls = _make_connector("myfiles")
        with patch.dict(sys.modules, {"core.v1": _core_mock("1.0.0")}):
            with patch("indexed.connectors.CONNECTORS", [cls]):
                names = list_connector_names()
        assert isinstance(names, list)
        assert "myfiles" in names

    def test_incompatible_connector_excluded_from_names(self):
        cls = _make_connector("old", min_core_version="99.0.0")
        with patch.dict(sys.modules, {"core.v1": _core_mock("1.0.0")}):
            with patch("indexed.connectors.CONNECTORS", [cls]):
                with warnings.catch_warnings(record=True):
                    warnings.simplefilter("always")
                    names = list_connector_names()
        assert "old" not in names


class TestCheckAllConnectorsCompatibility:
    """check_all_connectors_compatibility returns {name: (bool, str)} for all connectors."""

    @patch("indexed.connectors.CONNECTORS", [])
    def test_no_connectors_returns_empty_dict(self):
        assert check_all_connectors_compatibility() == {}

    def test_compatible_connector_reports_true(self):
        cls = _make_connector("files")
        with patch.dict(sys.modules, {"core.v1": _core_mock("2.0.0")}):
            with patch("indexed.connectors.CONNECTORS", [cls]):
                results = check_all_connectors_compatibility()
        is_compat, _ = results["files"]
        assert is_compat is True

    def test_incompatible_connector_reports_false(self):
        cls = _make_connector("old", min_core_version="99.0.0")
        with patch.dict(sys.modules, {"core.v1": _core_mock("1.0.0")}):
            with patch("indexed.connectors.CONNECTORS", [cls]):
                with warnings.catch_warnings(record=True):
                    warnings.simplefilter("always")
                    results = check_all_connectors_compatibility()
        is_compat, _ = results["old"]
        assert is_compat is False

    def test_includes_all_connectors_regardless_of_compatibility(self):
        """Results dict should contain entries for both compatible and incompatible."""
        cls1 = _make_connector("ok")
        cls2 = _make_connector("old", min_core_version="99.0.0")
        with patch.dict(sys.modules, {"core.v1": _core_mock("1.0.0")}):
            with patch("indexed.connectors.CONNECTORS", [cls1, cls2]):
                with warnings.catch_warnings(record=True):
                    warnings.simplefilter("always")
                    results = check_all_connectors_compatibility()
        assert "ok" in results
        assert "old" in results

    def test_connector_without_meta_skipped(self):
        class NoMeta:
            pass

        with patch("indexed.connectors.CONNECTORS", [NoMeta]):
            results = check_all_connectors_compatibility()
        assert len(results) == 0
