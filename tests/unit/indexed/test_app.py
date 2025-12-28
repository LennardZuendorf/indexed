"""Tests for main app entry point and initialization."""

from pathlib import Path
from unittest.mock import Mock, patch
import sys
import pytest
import typer
from typer.testing import CliRunner

from indexed.app import (
    _parse_early_storage_flags,
    _init_app,
    app,
)

runner = CliRunner()


class TestParseEarlyStorageFlags:
    """Test _parse_early_storage_flags function."""

    def test_parse_no_flags(self):
        """Should return (False, False) when no storage flags provided."""
        # Save original argv
        original_argv = sys.argv.copy()
        try:
            sys.argv = ["indexed", "index", "search", "test"]
            use_local, use_global = _parse_early_storage_flags()
            assert use_local is False
            assert use_global is False
        finally:
            sys.argv = original_argv

    def test_parse_local_flag(self):
        """Should extract --local flag."""
        original_argv = sys.argv.copy()
        try:
            sys.argv = ["indexed", "--local", "index", "search", "test"]
            use_local, use_global = _parse_early_storage_flags()
            assert use_local is True
            assert use_global is False
            # Flag should be removed from argv
            assert "--local" not in sys.argv
        finally:
            sys.argv = original_argv

    def test_parse_global_flag(self):
        """Should extract --global flag."""
        original_argv = sys.argv.copy()
        try:
            sys.argv = ["indexed", "--global", "index", "search", "test"]
            use_local, use_global = _parse_early_storage_flags()
            assert use_local is False
            assert use_global is True
            # Flag should be removed from argv
            assert "--global" not in sys.argv
        finally:
            sys.argv = original_argv

    def test_parse_both_flags_raises(self):
        """Should error when both --local and --global are provided."""
        original_argv = sys.argv.copy()
        try:
            sys.argv = ["indexed", "--local", "--global", "index", "search", "test"]
            use_local, use_global = _parse_early_storage_flags()
            # Both should be parsed, but error is handled in _init_app
            assert use_local is True
            assert use_global is True
        finally:
            sys.argv = original_argv


class TestInitApp:
    """Test _init_app callback."""

    @patch("indexed.app.setup_root_logger")
    @patch("indexed.app.os.getenv")
    def test_init_app_sets_up_logging(self, mock_getenv, mock_setup_logger):
        """Should set up logging with correct parameters."""

        # Mock getenv to return None for INDEXED_LOG_LEVEL and "false" for INDEXED_LOG_JSON
        def getenv_side_effect(key, default=None):
            if key == "INDEXED_LOG_LEVEL":
                return None
            elif key == "INDEXED_LOG_JSON":
                return default if default else "false"
            return default

        mock_getenv.side_effect = getenv_side_effect

        ctx = Mock()
        ctx.invoked_subcommand = "search"
        ctx.resilient_parsing = False

        _init_app(ctx, verbose=False, log_level=None, json_logs=False)

        # Should have called setup_root_logger
        mock_setup_logger.assert_called_once()

    @patch("indexed.app.setup_root_logger")
    @patch("indexed.app.os.getenv")
    def test_init_app_verbose_mode(self, mock_getenv, mock_setup_logger):
        """Should set INFO logging level in verbose mode."""

        # Mock getenv to return None for INDEXED_LOG_LEVEL and "false" for INDEXED_LOG_JSON
        def getenv_side_effect(key, default=None):
            if key == "INDEXED_LOG_LEVEL":
                return None
            elif key == "INDEXED_LOG_JSON":
                return default if default else "false"
            return default

        mock_getenv.side_effect = getenv_side_effect

        ctx = Mock()
        ctx.invoked_subcommand = "search"
        ctx.resilient_parsing = False

        _init_app(ctx, verbose=True, log_level=None, json_logs=False)

        # Should have called setup_root_logger with INFO level
        call_kwargs = mock_setup_logger.call_args.kwargs
        assert call_kwargs["level_str"] == "INFO"

    @patch("indexed.app.setup_root_logger")
    @patch("indexed.app.os.getenv")
    def test_init_app_json_logs(self, mock_getenv, mock_setup_logger):
        """Should enable JSON logging when --json-logs flag provided."""

        # Mock getenv to return None for INDEXED_LOG_LEVEL and "false" for INDEXED_LOG_JSON
        def getenv_side_effect(key, default=None):
            if key == "INDEXED_LOG_LEVEL":
                return None
            elif key == "INDEXED_LOG_JSON":
                return default if default else "false"
            return default

        mock_getenv.side_effect = getenv_side_effect

        ctx = Mock()
        ctx.invoked_subcommand = "search"
        ctx.resilient_parsing = False

        _init_app(ctx, verbose=False, log_level=None, json_logs=True)

        # Should have called setup_root_logger with json_mode=True
        call_kwargs = mock_setup_logger.call_args.kwargs
        assert call_kwargs["json_mode"] is True

    @patch("indexed.app._prompt_console")
    @patch("indexed.app.setup_root_logger")
    @patch("indexed.app.os.getenv")
    def test_init_app_both_flags_error(
        self, mock_getenv, mock_setup_logger, mock_console
    ):
        """Should error when both --local and --global flags provided."""

        # Mock getenv to return None for INDEXED_LOG_LEVEL and "false" for INDEXED_LOG_JSON
        def getenv_side_effect(key, default=None):
            if key == "INDEXED_LOG_LEVEL":
                return None
            elif key == "INDEXED_LOG_JSON":
                return default if default else "false"
            return default

        mock_getenv.side_effect = getenv_side_effect

        # Simulate both flags being set globally
        from indexed import app as app_module

        original_local = app_module._EARLY_USE_LOCAL
        original_global = app_module._EARLY_USE_GLOBAL

        try:
            app_module._EARLY_USE_LOCAL = True
            app_module._EARLY_USE_GLOBAL = True

            ctx = Mock()
            ctx.invoked_subcommand = "search"
            ctx.resilient_parsing = False

            with pytest.raises(typer.Exit):
                _init_app(ctx, verbose=False, log_level=None, json_logs=False)

            # Should have printed error message
            mock_console.print.assert_called()
        finally:
            app_module._EARLY_USE_LOCAL = original_local
            app_module._EARLY_USE_GLOBAL = original_global


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


class TestMigrateCommand:
    """Test migrate command."""

    @patch("indexed.utils.migration.migrate_legacy_data")
    @patch("indexed.utils.migration.has_legacy_data")
    @patch("indexed_config.get_global_root")
    def test_migrate_no_legacy_data(
        self, mock_get_global, mock_has_legacy, mock_migrate
    ):
        """Should inform user when no legacy data exists."""
        mock_has_legacy.return_value = False

        result = runner.invoke(app, ["migrate"])

        # Should complete without error
        assert result.exit_code == 0
        assert "legacy" in result.stdout.lower() or "no" in result.stdout.lower()
        mock_migrate.assert_not_called()

    @patch("indexed.utils.migration.migrate_legacy_data")
    @patch("indexed.utils.migration.has_legacy_data")
    @patch("indexed_config.get_global_root")
    def test_migrate_with_legacy_data(
        self, mock_get_global, mock_has_legacy, mock_migrate
    ):
        """Should call migrate function when legacy data exists."""
        mock_has_legacy.return_value = True
        mock_get_global.return_value = Path("~/.indexed")

        result = runner.invoke(app, ["migrate"])

        # Should complete successfully
        assert result.exit_code == 0
        mock_migrate.assert_called_once()

    @patch("indexed.utils.migration.migrate_legacy_data")
    @patch("indexed.utils.migration.has_legacy_data")
    @patch("indexed_config.get_global_root")
    def test_migrate_dry_run(self, mock_get_global, mock_has_legacy, mock_migrate):
        """Should pass --dry-run flag to migrate function."""
        mock_has_legacy.return_value = True
        mock_get_global.return_value = Path("~/.indexed")

        result = runner.invoke(app, ["migrate", "--dry-run"])

        # Should complete successfully
        assert result.exit_code == 0
        # Verify migrate was called with dry_run=True
        call_kwargs = mock_migrate.call_args.kwargs
        assert call_kwargs.get("dry_run") is True


class TestMainFunction:
    """Test main entry point function."""

    @patch("indexed.app.app")
    @patch("indexed.app._parse_early_storage_flags")
    @patch("indexed.app.print_indexed_banner")
    def test_main_calls_parse_early_flags(
        self, mock_banner, mock_parse_flags, mock_app
    ):
        """Should call _parse_early_storage_flags in main."""
        mock_parse_flags.return_value = (False, False)
        original_argv = sys.argv.copy()
        try:
            sys.argv = ["indexed", "--help"]
            from indexed.app import main

            main()

            # Should have parsed early flags
            mock_parse_flags.assert_called_once()
        finally:
            sys.argv = original_argv
