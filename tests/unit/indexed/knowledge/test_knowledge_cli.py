"""Tests for knowledge CLI docs command."""

import pytest
from unittest.mock import patch
from typer.testing import CliRunner

from indexed.knowledge.cli import app

runner = CliRunner()


class TestDocsCommand:
    """Tests for the docs command."""

    @patch("indexed.knowledge.cli.webbrowser.open")
    def test_docs_opens_browser_successfully(self, mock_open):
        """docs command should open browser and exit with code 0."""
        mock_open.return_value = True

        result = runner.invoke(app, ["docs"])

        mock_open.assert_called_once()
        assert result.exit_code == 0

    @patch("indexed.knowledge.cli.webbrowser.open")
    def test_docs_opens_correct_url(self, mock_open):
        """docs command should open the indexing documentation URL."""
        mock_open.return_value = True

        runner.invoke(app, ["docs"])

        called_url = mock_open.call_args[0][0]
        assert "indexed" in called_url
        assert called_url.startswith("https://")

    @patch("indexed.knowledge.cli.webbrowser.open")
    def test_docs_browser_failure_exits_with_code_1(self, mock_open):
        """docs command should exit with code 1 when browser raises."""
        mock_open.side_effect = Exception("browser not available")

        result = runner.invoke(app, ["docs"])

        assert result.exit_code == 1
