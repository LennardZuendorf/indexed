"""Tests for knowledge CLI docs command."""

from unittest.mock import patch
from typer.testing import CliRunner

from indexed.cli.knowledge.cli import app

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
        result = runner.invoke(app, ["search", "--help"])

        assert result.exit_code == 0
        assert "Examples:" in result.stdout

    def test_inspect_help_shows_examples(self):
        result = runner.invoke(app, ["inspect", "--help"])

        assert result.exit_code == 0
        assert "Examples:" in result.stdout

    def test_remove_help_shows_examples(self):
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
