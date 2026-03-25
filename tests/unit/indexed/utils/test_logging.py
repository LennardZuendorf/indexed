"""Tests for CLI logging utilities."""

import pytest
from loguru import logger as loguru_logger

from indexed.utils.logging import (
    setup_logging,
    setup_root_logger,
    is_verbose_mode,
    enable_status_capture,
    disable_status_capture,
)


@pytest.fixture(autouse=True)
def reset_logging_state():
    """Disable any active capture before and after each test."""
    disable_status_capture()
    yield
    disable_status_capture()


class TestSetupLogging:
    """Tests for setup_logging via the public is_verbose_mode() indicator."""

    def test_verbose_flag_enables_verbose_mode(self):
        setup_logging(verbose=True)
        assert is_verbose_mode() is True

    def test_debug_flag_enables_verbose_mode(self):
        setup_logging(debug=True)
        assert is_verbose_mode() is True

    def test_quiet_flag_disables_verbose_mode(self):
        setup_logging(quiet=True)
        assert is_verbose_mode() is False

    def test_defaults_disable_verbose_mode(self):
        setup_logging()
        assert is_verbose_mode() is False

    def test_quiet_overrides_verbose(self):
        """quiet=True should win over verbose=True."""
        setup_logging(verbose=True, quiet=True)
        assert is_verbose_mode() is False


class TestSetupRootLogger:
    """Tests for setup_root_logger."""

    def test_info_level_enables_verbose_mode(self):
        setup_root_logger("INFO")
        assert is_verbose_mode() is True

    def test_debug_level_enables_verbose_mode(self):
        setup_root_logger("DEBUG")
        assert is_verbose_mode() is True

    def test_warning_level_disables_verbose_mode(self):
        setup_root_logger("WARNING")
        assert is_verbose_mode() is False

    def test_error_level_disables_verbose_mode(self):
        setup_root_logger("ERROR")
        assert is_verbose_mode() is False

    def test_default_disables_verbose_mode(self):
        setup_root_logger()
        assert is_verbose_mode() is False

    def test_json_mode_flag_accepted_without_error(self):
        setup_root_logger("DEBUG", json_mode=True)
        assert is_verbose_mode() is True


class TestStatusCapture:
    """Tests for enable_status_capture and disable_status_capture."""

    def test_enable_returns_int_sink_id(self):
        sink_id = enable_status_capture(lambda msg: None)
        assert isinstance(sink_id, int)

    def test_info_messages_forwarded_to_callback(self):
        """INFO log messages emitted via loguru should reach the callback."""
        received = []
        setup_root_logger("INFO")
        enable_status_capture(received.append)

        loguru_logger.info("hello from test")

        assert any("hello from test" in msg for msg in received)

    def test_callback_not_called_after_disable(self):
        """After disable_status_capture, callback should not receive further messages."""
        received = []
        setup_root_logger("INFO")
        enable_status_capture(received.append)
        disable_status_capture()

        loguru_logger.info("should not arrive")

        assert not any("should not arrive" in msg for msg in received)

    def test_disable_is_idempotent(self):
        """Calling disable_status_capture multiple times should not raise."""
        disable_status_capture()
        disable_status_capture()

    def test_reconfigured_logger_still_forwards_messages(self):
        """After re-configuring loguru while capture is active, messages still forwarded."""
        received = []
        enable_status_capture(received.append)
        setup_root_logger("INFO")  # Re-register loguru handlers

        loguru_logger.info("after reconfigure")

        assert any("after reconfigure" in msg for msg in received)
