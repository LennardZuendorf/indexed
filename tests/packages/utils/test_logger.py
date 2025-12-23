"""Tests for logger utility module.

Tests the Loguru-based logging configuration.
"""

from loguru import logger
from utils.logger import setup_root_logger, is_verbose_mode, get_current_log_level


class TestSetupRootLogger:
    """Test logger configuration."""

    def teardown_method(self):
        """Clean up logger state after each test."""
        # Remove all handlers to reset state
        logger.remove()

    def test_configures_default_warning_level(self):
        """Should default to WARNING level."""
        setup_root_logger()

        level = get_current_log_level()
        assert level == "WARNING"

    def test_configures_custom_level(self):
        """Should accept custom log level."""
        setup_root_logger(level_str="DEBUG")

        level = get_current_log_level()
        assert level == "DEBUG"

    def test_normalizes_level_to_uppercase(self):
        """Should normalize log level to uppercase."""
        setup_root_logger(level_str="info")

        level = get_current_log_level()
        assert level == "INFO"

    def test_allows_reconfiguration(self):
        """Should allow changing log level after initial setup."""
        setup_root_logger(level_str="WARNING")
        assert get_current_log_level() == "WARNING"

        # Reconfigure with different level
        setup_root_logger(level_str="DEBUG")
        assert get_current_log_level() == "DEBUG"

    def test_json_mode_configuration(self):
        """Should configure JSON output mode."""
        # This just verifies no errors occur
        setup_root_logger(level_str="INFO", json_mode=True)

        assert get_current_log_level() == "INFO"

    def test_verbose_mode_detection_for_info(self):
        """Should detect INFO as verbose mode."""
        setup_root_logger(level_str="INFO")

        assert is_verbose_mode() is True

    def test_verbose_mode_detection_for_debug(self):
        """Should detect DEBUG as verbose mode."""
        setup_root_logger(level_str="DEBUG")

        assert is_verbose_mode() is True

    def test_verbose_mode_false_for_warning(self):
        """Should not consider WARNING as verbose mode."""
        setup_root_logger(level_str="WARNING")

        assert is_verbose_mode() is False

    def test_verbose_mode_false_for_error(self):
        """Should not consider ERROR as verbose mode."""
        setup_root_logger(level_str="ERROR")

        assert is_verbose_mode() is False


class TestGetCurrentLogLevel:
    """Test log level getter."""

    def teardown_method(self):
        """Clean up logger state."""
        logger.remove()

    def test_returns_configured_level(self):
        """Should return currently configured level."""
        setup_root_logger(level_str="INFO")

        assert get_current_log_level() == "INFO"

    def test_tracks_level_changes(self):
        """Should track level across reconfigurations."""
        setup_root_logger(level_str="WARNING")
        assert get_current_log_level() == "WARNING"

        setup_root_logger(level_str="DEBUG")
        assert get_current_log_level() == "DEBUG"

        setup_root_logger(level_str="ERROR")
        assert get_current_log_level() == "ERROR"


class TestIsVerboseMode:
    """Test verbose mode detection."""

    def teardown_method(self):
        """Clean up logger state."""
        logger.remove()

    def test_verbose_levels(self):
        """Should return True for INFO and DEBUG."""
        verbose_levels = ["INFO", "DEBUG"]

        for level in verbose_levels:
            setup_root_logger(level_str=level)
            assert is_verbose_mode() is True, f"Expected {level} to be verbose"

    def test_non_verbose_levels(self):
        """Should return False for WARNING and ERROR."""
        non_verbose_levels = ["WARNING", "ERROR"]

        for level in non_verbose_levels:
            setup_root_logger(level_str=level)
            assert is_verbose_mode() is False, f"Expected {level} to not be verbose"
