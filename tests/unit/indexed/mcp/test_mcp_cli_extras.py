"""Extra MCP CLI coverage."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from indexed.mcp.cli import docs, main

runner = CliRunner()


def test_main_invokes_run_when_no_subcommand() -> None:
    ctx = MagicMock()
    ctx.invoked_subcommand = None
    with patch("indexed.mcp.cli.run_impl") as mock_run:
        main(ctx)
    mock_run.assert_called_once()


@patch("indexed.mcp.cli.webbrowser.open")
@patch("indexed.mcp.cli.print_success")
def test_docs_opens_browser(mock_success: MagicMock, mock_open: MagicMock) -> None:
    docs()
    mock_open.assert_called_once()
    mock_success.assert_called_once()


@patch("indexed.mcp.cli.webbrowser.open", side_effect=OSError("no browser"))
@patch("indexed.mcp.cli.print_error")
def test_docs_browser_failure_exits(
    mock_error: MagicMock, mock_open: MagicMock
) -> None:
    with pytest.raises(typer.Exit) as exc:
        docs()
    assert exc.value.exit_code == 1
    mock_error.assert_called_once()
