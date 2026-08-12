"""Tests for main app entry point and initialization."""

from unittest.mock import Mock, patch
import sys
from typer.testing import CliRunner

from indexed.cli.app import (
    _init_app,
    app,
)

runner = CliRunner()


class TestInitApp:
    """Test _init_app callback."""

    @patch("indexed.cli.app.bootstrap_logging")
    def test_init_app_sets_up_logging(self, mock_setup_logger, mock_getenv_defaults):
        """Should set up logging with correct parameters."""

        ctx = Mock()
        ctx.invoked_subcommand = "search"
        ctx.resilient_parsing = False
        ctx.ensure_object = Mock()
        ctx.obj = {}

        _init_app(
            ctx,
            verbose=False,
            log_level=None,
            json_logs=False,
        )

        mock_setup_logger.assert_called_once()

    @patch("indexed.cli.app.bootstrap_logging")
    def test_init_app_verbose_mode(self, mock_setup_logger, mock_getenv_defaults):
        """Should set INFO logging level in verbose mode."""

        ctx = Mock()
        ctx.invoked_subcommand = "search"
        ctx.resilient_parsing = False
        ctx.ensure_object = Mock()
        ctx.obj = {}

        _init_app(
            ctx,
            verbose=True,
            log_level=None,
            json_logs=False,
        )

        call_kwargs = mock_setup_logger.call_args.kwargs
        assert call_kwargs["level"] == "INFO"

    @patch("indexed.cli.app.bootstrap_logging")
    def test_init_app_json_logs(self, mock_setup_logger, mock_getenv_defaults):
        """Should enable JSON logging when --json-logs flag provided."""

        ctx = Mock()
        ctx.invoked_subcommand = "search"
        ctx.resilient_parsing = False
        ctx.ensure_object = Mock()
        ctx.obj = {}

        _init_app(
            ctx,
            verbose=False,
            log_level=None,
            json_logs=True,
        )

        call_kwargs = mock_setup_logger.call_args.kwargs
        assert call_kwargs["json_mode"] is True

    def test_local_flag_is_rejected_as_an_unknown_option(self):
        """workspace-profile/1 R1: `--local` no longer exists on any command."""
        for argv in (
            ["--local", "inspect"],
            ["index", "create", "files", "--local", "--collection", "x"],
        ):
            result = runner.invoke(app, argv)
            assert result.exit_code != 0, argv
            assert "No such option: --local" in result.output, argv

    def test_no_storage_mode_is_stashed_on_the_context(self):
        """workspace-profile/1 R1: ctx.obj carries no mode_override any more."""
        ctx = Mock()
        ctx.invoked_subcommand = "search"
        ctx.resilient_parsing = False
        ctx.ensure_object = Mock()
        ctx.obj = {}

        with patch("indexed.cli.app.bootstrap_logging"):
            _init_app(ctx, verbose=False, log_level=None, json_logs=False)

        assert "mode_override" not in ctx.obj


class TestAppCommands:
    """Test app command registration."""

    def test_help_shows_commands(self):
        """Should show help text with available commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "index create" in result.stdout or "INDEX" in result.stdout

    def test_index_command_exists(self):
        """Should have index command."""
        result = runner.invoke(app, ["index", "--help"])
        assert result.exit_code == 0

    def test_config_command_exists(self):
        """Should have config command."""
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0

    def test_mcp_command_exists(self):
        """Should have mcp command."""
        result = runner.invoke(app, ["mcp", "--help"])
        assert result.exit_code == 0


class TestMainFunction:
    """Test main entry point function."""

    @patch("indexed.cli.app.app")
    @patch("indexed.cli.app.print_indexed_banner")
    def test_main_calls_app(self, mock_banner, mock_app):
        """Should call app() in main."""
        original_argv = sys.argv.copy()
        try:
            sys.argv = ["indexed", "--help"]
            from indexed.cli.app import main

            main()

            mock_app.assert_called_once()
        finally:
            sys.argv = original_argv
