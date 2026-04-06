"""Tests for the debug command module."""

from unittest.mock import patch, MagicMock

from indexed.debug import get_build_info, _pkg_version, _module_version


class TestGetBuildInfo:
    def test_returns_dev_fallback_when_no_build_meta(self):
        with patch.dict("sys.modules", {"indexed._build_meta": None}):
            with patch(
                "indexed.debug.get_build_info",
                wraps=get_build_info,
            ):
                # Force ImportError by removing the module
                import sys

                saved = sys.modules.pop("indexed._build_meta", None)
                try:
                    ts, commit = get_build_info()
                    assert ts == "dev (editable install)"
                    assert commit == "n/a"
                finally:
                    if saved is not None:
                        sys.modules["indexed._build_meta"] = saved

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


class TestModuleVersion:
    def test_returns_dist_version_when_available(self):
        with patch("indexed.debug._pkg_version", return_value="1.2.3"):
            result = _module_version("some_module")
            assert result == "1.2.3"

    def test_falls_back_to_module_attribute(self):
        mock_mod = MagicMock()
        mock_mod.__version__ = "0.5.0"

        with patch("indexed.debug._pkg_version", return_value="not installed"):
            with patch("importlib.import_module", return_value=mock_mod):
                result = _module_version("some_module")
                assert result == "0.5.0"

    def test_returns_bundled_when_no_version_attr(self):
        mock_mod = MagicMock(spec=[])  # no __version__

        with patch("indexed.debug._pkg_version", return_value="not installed"):
            with patch("importlib.import_module", return_value=mock_mod):
                result = _module_version("some_module")
                assert result == "bundled"

    def test_returns_not_installed_when_import_fails(self):
        with patch("indexed.debug._pkg_version", return_value="not installed"):
            with patch("importlib.import_module", side_effect=ImportError):
                result = _module_version("nonexistent_module")
                assert result == "not installed"

    def test_custom_version_attr(self):
        mock_mod = MagicMock()
        mock_mod.VERSION = "2.0.0"

        with patch("indexed.debug._pkg_version", return_value="not installed"):
            with patch("importlib.import_module", return_value=mock_mod):
                result = _module_version("some_module", version_attr="VERSION")
                assert result == "2.0.0"


class TestDebugCommand:
    def test_json_output(self):
        with patch("indexed.debug.console") as mock_console:
            with patch("indexed.debug.get_build_info", return_value=("dev", "n/a")):
                with patch("indexed.debug._pkg_version", return_value="0.1.0"):
                    with patch(
                        "indexed.debug._module_version", return_value="bundled"
                    ):
                        from indexed.debug import debug

                        debug(json_output=True)

                        mock_console.print_json.assert_called_once()
                        call_arg = mock_console.print_json.call_args[0][0]
                        import json

                        data = json.loads(call_arg)
                        assert "build" in data
                        assert "environment" in data
                        assert "dependencies" in data

    def test_rich_output(self):
        with patch("indexed.debug.console") as mock_console:
            with patch("indexed.debug.get_build_info", return_value=("dev", "n/a")):
                with patch("indexed.debug._pkg_version", return_value="0.1.0"):
                    with patch(
                        "indexed.debug._module_version", return_value="bundled"
                    ):
                        with patch(
                            "indexed.debug.create_key_value_panel"
                        ) as mock_panel:
                            mock_panel.return_value = "panel"
                            from indexed.debug import debug

                            debug(json_output=False)

                            assert mock_console.print.called
                            assert mock_panel.call_count == 3
