"""Tests for knowledge CLI docs command and per-command --help rendering."""

from unittest.mock import patch
import pytest
from typer.testing import CliRunner

from indexed.cli.app import app as root_app
from indexed.cli.knowledge.cli import app

# Module-level marker (same idiom as tests/unit/indexed/config/test_cli.py) so
# `pytest -m unit` selects every class here, not just one.
pytestmark = pytest.mark.unit

runner = CliRunner()


class TestDocsCommand:
    """Tests for the docs command."""

    @patch("indexed.cli.knowledge.cli.webbrowser.open")
    def test_docs_opens_browser_successfully(self, mock_open):
        """docs command should open browser and exit with code 0."""
        mock_open.return_value = True

        result = runner.invoke(app, ["docs"])

        mock_open.assert_called_once()
        assert result.exit_code == 0

    @patch("indexed.cli.knowledge.cli.webbrowser.open")
    def test_docs_opens_correct_url(self, mock_open):
        """docs command should open the indexing documentation URL."""
        mock_open.return_value = True

        runner.invoke(app, ["docs"])

        called_url = mock_open.call_args[0][0]
        assert "indexed" in called_url
        assert called_url.startswith("https://")

    @patch("indexed.cli.knowledge.cli.webbrowser.open")
    def test_docs_browser_failure_exits_with_code_1(self, mock_open):
        """docs command should exit with code 1 when browser raises."""
        mock_open.side_effect = Exception("browser not available")

        result = runner.invoke(app, ["docs"])

        assert result.exit_code == 1


class TestCommandHelpShowsDocstring:
    """`--help` for each knowledge command renders its own full docstring
    (including its Examples: block, where present) instead of the old
    one-line ``help=`` override (core-v2-discoverability/5, R5/R7)."""

    def test_migrate_help_shows_safety_explanation_and_examples(self):
        """`migrate --help` must reassure the user before a data-changing op."""
        result = runner.invoke(app, ["migrate", "--help"])

        assert result.exit_code == 0
        assert "v1-backup" in result.stdout
        assert "rollback-safe" in result.stdout
        assert "Examples:" in result.stdout

    def test_search_help_shows_examples(self):
        """`search --help` renders its docstring's Examples: block."""
        result = runner.invoke(app, ["search", "--help"])

        assert result.exit_code == 0
        assert "Examples:" in result.stdout

    def test_inspect_help_shows_examples(self):
        """`inspect --help` renders its docstring's Examples: block."""
        result = runner.invoke(app, ["inspect", "--help"])

        assert result.exit_code == 0
        assert "Examples:" in result.stdout

    def test_remove_help_shows_examples(self):
        """`remove --help` renders its docstring's Examples: block."""
        result = runner.invoke(app, ["remove", "--help"])

        assert result.exit_code == 0
        assert "Examples:" in result.stdout

    def test_update_help_shows_docstring_no_regression(self):
        """update's docstring is currently one line — no Examples: block yet,
        but it must still render (not fall back to a generic override)."""
        result = runner.invoke(app, ["update", "--help"])

        assert result.exit_code == 0
        assert "Refresh and re-index a collection" in result.stdout

    def test_index_help_listing_uses_docstring_first_lines(self):
        """`indexed index --help`'s one-line command listing derives from
        each docstring's first line and still reads sensibly for all five."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "Search across collections using semantic similarity." in result.stdout
        assert (
            "Show all indexed collections or inspect a specific collection."
            in result.stdout
        )
        assert "Refresh and re-index a collection or all collections." in result.stdout
        assert "Remove a collection from the index." in result.stdout
        assert (
            "Convert a v1 collection to the v2 engine (offline by default)."
            in result.stdout
        )


class TestCreateEngineFlagHelp:
    """`--engine` is discoverable in `--help` at BOTH surfaces R1 names — the
    `index create files` leaf and the `index create` group — not only on the
    root callback. Driven through the real root app so the asserted command
    paths are the ones a user actually types (issue #188)."""

    def test_index_create_files_help_shows_engine_flag(self):
        """`index create files --help` lists the leaf-level `--engine`."""
        result = runner.invoke(root_app, ["index", "create", "files", "--help"])

        assert result.exit_code == 0, result.stdout
        assert "--engine" in result.stdout

    def test_index_create_group_help_shows_engine_flag(self):
        """`index create --help` lists the group-level `--engine`, one level up
        the tree — where issue #188 says the user looks for it."""
        result = runner.invoke(root_app, ["index", "create", "--help"])

        assert result.exit_code == 0, result.stdout
        assert "--engine" in result.stdout
