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
            local=False,
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
            local=False,
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
            local=False,
            verbose=False,
            log_level=None,
            json_logs=True,
        )

        call_kwargs = mock_setup_logger.call_args.kwargs
        assert call_kwargs["json_mode"] is True

    @patch("indexed.cli.app.bootstrap_logging")
    def test_init_app_local_sets_mode_override(
        self, mock_setup_logger, mock_getenv_defaults
    ):
        """Should set mode_override to 'local' on ctx.obj when --local is passed."""
        ctx = Mock()
        ctx.invoked_subcommand = "search"
        ctx.resilient_parsing = False
        ctx.ensure_object = Mock()
        ctx.obj = {}

        with patch("indexed.config.has_local_config", return_value=True):
            _init_app(
                ctx,
                local=True,
                verbose=False,
                log_level=None,
                json_logs=False,
            )

        assert ctx.obj["mode_override"] == "local"

    @patch("indexed.cli.app.bootstrap_logging")
    def test_init_app_no_flags_sets_none(self, mock_setup_logger, mock_getenv_defaults):
        """Should set mode_override to None when no storage flags provided."""
        ctx = Mock()
        ctx.invoked_subcommand = "search"
        ctx.resilient_parsing = False
        ctx.ensure_object = Mock()
        ctx.obj = {}

        _init_app(
            ctx,
            local=False,
            verbose=False,
            log_level=None,
            json_logs=False,
        )

        assert ctx.obj["mode_override"] is None


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
