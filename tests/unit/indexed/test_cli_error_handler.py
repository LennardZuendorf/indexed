"""Tests for IndexedError handling at the CLI boundary."""

from unittest.mock import MagicMock, patch

import pytest
from indexed.config.errors import (
    ConfigValidationError,
    ConfigurationError,
    IndexedError,
    StorageConflictError,
    StorageError,
)

from indexed.cli.errors import (
    CLIError,
    EXIT_CODES,
    exit_code_for,
    format_cli_error,
    mcp_error_envelope,
)
from indexed.cli.utils.components import get_error_style


class TestErrorHelpers:
    """Tests for error formatting and exit-code mapping."""

    def test_format_cli_error_returns_message(self) -> None:
        err = ConfigurationError("bad config")
        assert format_cli_error(err) == "bad config"

    def test_mcp_error_envelope_includes_type(self) -> None:
        err = StorageError("disk full")
        assert mcp_error_envelope(err) == {
            "error": "disk full",
            "type": "StorageError",
        }

    @pytest.mark.parametrize(
        ("exc", "expected_code"),
        [
            (ConfigurationError("cfg"), EXIT_CODES[ConfigurationError]),
            (ConfigValidationError("path", "detail"), EXIT_CODES[ConfigurationError]),
            (StorageError("store"), EXIT_CODES[StorageError]),
            (StorageConflictError("conflict"), EXIT_CODES[StorageError]),
            (CLIError("cli"), 1),
            (IndexedError("generic"), 1),
        ],
    )
    def test_exit_code_for(self, exc: IndexedError, expected_code: int) -> None:
        assert exit_code_for(exc) == expected_code


class TestMainErrorHandler:
    """Tests for IndexedError handling in main()."""

    @patch("indexed.cli.app.app")
    @patch("indexed.cli.app.bootstrap_logging")
    @patch("indexed.cli.app._shared_console")
    def test_main_maps_configuration_error_to_exit_code_2(
        self,
        mock_console: MagicMock,
        mock_bootstrap: MagicMock,
        mock_app: MagicMock,
    ) -> None:
        mock_app.side_effect = ConfigurationError("invalid connector")

        with pytest.raises(SystemExit) as exc_info:
            from indexed.cli.app import main

            main()

        assert exc_info.value.code == 2
        mock_console.print.assert_called_once_with(
            "invalid connector",
            style=get_error_style(),
        )

    @patch("indexed.cli.app.app")
    @patch("indexed.cli.app.bootstrap_logging")
    @patch("indexed.cli.app._shared_console")
    def test_main_maps_storage_error_to_exit_code_3(
        self,
        mock_console: MagicMock,
        mock_bootstrap: MagicMock,
        mock_app: MagicMock,
    ) -> None:
        mock_app.side_effect = StorageError("storage unavailable")

        with pytest.raises(SystemExit) as exc_info:
            from indexed.cli.app import main

            main()

        assert exc_info.value.code == 3
        mock_console.print.assert_called_once_with(
            "storage unavailable",
            style=get_error_style(),
        )

    @patch("indexed.cli.app.app")
    @patch("indexed.cli.app.bootstrap_logging")
    def test_main_propagates_unexpected_errors(
        self,
        mock_bootstrap: MagicMock,
        mock_app: MagicMock,
    ) -> None:
        mock_app.side_effect = RuntimeError("unexpected")

        with pytest.raises(RuntimeError, match="unexpected"):
            from indexed.cli.app import main

            main()
