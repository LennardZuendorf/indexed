"""Tests for the debug command module."""

import builtins
import json
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from indexed.cli.debug import _pkg_version, get_build_info

_real_import = builtins.__import__


def _import_without_build_meta(
    name: str,
    globals: dict[str, Any] | None = None,
    locals: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> types.ModuleType:
    if name == "indexed._build_meta" or (
        name == "indexed" and fromlist and "_build_meta" in fromlist
    ):
        raise ImportError("indexed._build_meta not available")
    return _real_import(name, globals, locals, fromlist, level)  # type: ignore[return-value]


class TestGetBuildInfo:
    def test_returns_dev_fallback_when_no_build_meta(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys
        import indexed

        monkeypatch.delitem(sys.modules, "indexed._build_meta", raising=False)
        monkeypatch.delattr(indexed, "_build_meta", raising=False)
        monkeypatch.setattr(builtins, "__import__", _import_without_build_meta)
        ts, commit = get_build_info()
        assert ts == "dev (editable install)"
        assert commit == "n/a"

    def test_returns_build_meta_when_available(self):
        mock_module = MagicMock()
        mock_module.BUILD_TIMESTAMP = "2026-01-01T00:00:00"
        mock_module.BUILD_COMMIT = "abc123"

        with patch.dict("sys.modules", {"indexed._build_meta": mock_module}):
            ts, commit = get_build_info()
            assert ts == "2026-01-01T00:00:00"
            assert commit == "abc123"


class TestPkgVersion:
    def test_returns_version_for_installed_package(self):
        # typer is installed in the environment
        result = _pkg_version("typer")
        assert result != "not installed"

    def test_returns_not_installed_for_missing_package(self):
        result = _pkg_version("nonexistent-package-xyz-12345")
        assert result == "not installed"

    def test_reports_the_single_distribution_version(self):
        # Post-collapse the wheel ships as one distribution: indexed-sh.
        # The old import name "indexed" is NOT a distribution.
        assert _pkg_version("indexed-sh") != "not installed"
        assert _pkg_version("indexed") == "not installed"


class TestDebugCommand:
    def test_json_output_reports_real_version_and_external_deps(self):
        # Version must resolve via the distribution name "indexed-sh", and the
        # dependency section must list external deps only — no phantom
        # workspace sub-packages (indexed-core, etc.) that no longer exist.
        def fake_pkg_version(name: str) -> str:
            return "0.0.5" if name == "indexed-sh" else f"v-{name}"

        with patch("indexed.cli.debug.console") as mock_console:
            with patch("indexed.cli.debug.get_build_info", return_value=("dev", "n/a")):
                with patch(
                    "indexed.cli.debug._pkg_version", side_effect=fake_pkg_version
                ):
                    from indexed.cli.debug import debug

                    debug(json_output=True)

                    mock_console.print_json.assert_called_once()
                    data = json.loads(mock_console.print_json.call_args[0][0])
                    assert data["build"]["Version"] == "0.0.5"
                    deps = data["dependencies"]
                    assert "indexed-core" not in deps
                    assert "indexed-connectors" not in deps
                    assert "faiss-cpu" in deps

    def test_rich_output(self):
        with patch("indexed.cli.debug.console") as mock_console:
            with patch("indexed.cli.debug.get_build_info", return_value=("dev", "n/a")):
                with patch("indexed.cli.debug._pkg_version", return_value="0.1.0"):
                    with patch(
                        "indexed.cli.debug.create_key_value_panel"
                    ) as mock_panel:
                        mock_panel.return_value = "panel"
                        from indexed.cli.debug import debug

                        debug(json_output=False)

                        assert mock_console.print.called
                        assert mock_panel.call_count == 3
