"""Tests for the debug command module."""

import json
from unittest.mock import patch

from indexed.cli.debug import _pkg_version


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
            with patch("indexed.cli.debug._pkg_version", side_effect=fake_pkg_version):
                from indexed.cli.debug import debug

                debug(json_output=True)

                mock_console.print_json.assert_called_once()
                data = json.loads(mock_console.print_json.call_args[0][0])
                assert data["build"]["Version"] == "0.0.5"
                # The build section is truthful: only Version, no phantom
                # Build Timestamp / Build Commit sourced from a _build_meta
                # module the build no longer generates.
                assert set(data["build"]) == {"Version"}
                deps = data["dependencies"]
                assert "indexed-core" not in deps
                assert "indexed-connectors" not in deps
                assert "faiss-cpu" in deps

    def test_rich_output(self):
        with patch("indexed.cli.debug.console") as mock_console:
            with patch("indexed.cli.debug._pkg_version", return_value="0.1.0"):
                with patch("indexed.cli.debug.create_key_value_panel") as mock_panel:
                    mock_panel.return_value = "panel"
                    from indexed.cli.debug import debug

                    debug(json_output=False)

                    assert mock_console.print.called
                    assert mock_panel.call_count == 3
