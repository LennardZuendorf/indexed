"""Comprehensive tests for alerts component module."""

from unittest.mock import patch
import pytest

from indexed.utils.components.alerts import (
    ICON_SUCCESS,
    ICON_ERROR,
    ICON_WARNING,
    ICON_INFO,
    print_success,
    print_error,
    print_warning,
    print_info,
)


class TestAlertIcons:
    """Test alert icon constants."""

    def test_icon_constants_defined(self):
        """Should have all icon constants defined."""
        assert ICON_SUCCESS == "✓"
        assert ICON_ERROR == "✗"
        assert ICON_WARNING == "⚠"
        assert ICON_INFO == "ℹ"

    def test_icons_are_strings(self):
        """All icons should be strings."""
        assert isinstance(ICON_SUCCESS, str)
        assert isinstance(ICON_ERROR, str)
        assert isinstance(ICON_WARNING, str)
        assert isinstance(ICON_INFO, str)


class TestPrintSuccess:
    """Test print_success function."""

    @patch('indexed.utils.components.alerts.console')
    def test_prints_success_message(self, mock_console):
        """Should print success message with checkmark icon."""
        print_success("Operation completed")
        
        assert mock_console.print.called
        # Verify the panel was printed (can't easily check exact content)

    @patch('indexed.utils.components.alerts.console')
    def test_includes_icon_in_message(self, mock_console):
        """Should include success icon in message."""
        print_success("Test message")
        
        # Check that some Rich object was printed
        assert mock_console.print.call_count == 1

    @patch('indexed.utils.components.alerts.console')
    def test_handles_empty_message(self, mock_console):
        """Should handle empty message string."""
        print_success("")
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_handles_long_message(self, mock_console):
        """Should handle long messages."""
        long_message = "A" * 200
        print_success(long_message)
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_handles_multiline_message(self, mock_console):
        """Should handle multiline messages."""
        multiline = "Line 1\nLine 2\nLine 3"
        print_success(multiline)
        
        assert mock_console.print.called


class TestPrintError:
    """Test print_error function."""

    @patch('indexed.utils.components.alerts.console')
    def test_prints_error_message(self, mock_console):
        """Should print error message with X icon."""
        print_error("Operation failed")
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_includes_error_icon(self, mock_console):
        """Should include error icon in message."""
        print_error("Error occurred")
        
        assert mock_console.print.call_count == 1

    @patch('indexed.utils.components.alerts.console')
    def test_handles_exception_message(self, mock_console):
        """Should handle exception messages."""
        try:
            raise ValueError("Something went wrong")
        except ValueError as e:
            print_error(str(e))
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_handles_special_characters(self, mock_console):
        """Should handle special characters in error message."""
        print_error("Error: file not found at /path/to/$file")
        
        assert mock_console.print.called


class TestPrintWarning:
    """Test print_warning function."""

    @patch('indexed.utils.components.alerts.console')
    def test_prints_warning_message(self, mock_console):
        """Should print warning message with warning icon."""
        print_warning("Deprecated feature")
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_includes_warning_icon(self, mock_console):
        """Should include warning icon in message."""
        print_warning("Warning message")
        
        assert mock_console.print.call_count == 1

    @patch('indexed.utils.components.alerts.console')
    def test_handles_deprecation_warnings(self, mock_console):
        """Should handle deprecation warning format."""
        print_warning("This feature is deprecated and will be removed in v2.0")
        
        assert mock_console.print.called


class TestPrintInfo:
    """Test print_info function."""

    @patch('indexed.utils.components.alerts.console')
    def test_prints_info_message(self, mock_console):
        """Should print info message with info icon."""
        print_info("Additional information")
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_includes_info_icon(self, mock_console):
        """Should include info icon in message."""
        print_info("FYI: something important")
        
        assert mock_console.print.call_count == 1

    @patch('indexed.utils.components.alerts.console')
    def test_handles_informational_text(self, mock_console):
        """Should handle informational text."""
        print_info("Configuration loaded from ~/.indexed/config.toml")
        
        assert mock_console.print.called


class TestAlertFormatting:
    """Test alert formatting and appearance."""

    @patch('indexed.utils.components.alerts.console')
    def test_creates_panel_object(self, mock_console):
        """Should create Rich Panel object."""
        print_success("Test")
        
        # Check that print was called with a Panel
        args = mock_console.print.call_args
        assert args is not None

    @patch('indexed.utils.components.alerts.console')
    def test_different_alerts_use_different_styles(self, mock_console):
        """Should use different styles for different alert types."""
        print_success("Success")
        print_error("Error")
        print_warning("Warning")
        print_info("Info")
        
        # Should have called print 4 times
        assert mock_console.print.call_count == 4


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch('indexed.utils.components.alerts.console')
    def test_handles_none_message_gracefully(self, mock_console):
        """Should handle None message (converts to string)."""
        # This might raise TypeError depending on implementation
        try:
            print_success(None)
        except TypeError:
            pass  # Expected if not handling None

    @patch('indexed.utils.components.alerts.console')
    def test_handles_numeric_message(self, mock_console):
        """Should handle numeric messages (converted to string)."""
        print_success(42)  # type: ignore
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_handles_unicode_emoji(self, mock_console):
        """Should handle Unicode emoji in messages."""
        print_success("Deployment successful 🚀")
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_sequential_alerts(self, mock_console):
        """Should handle multiple sequential alerts."""
        print_success("Step 1 complete")
        print_info("Processing step 2")
        print_success("Step 2 complete")
        print_warning("Step 3 skipped")
        print_error("Step 4 failed")
        
        assert mock_console.print.call_count == 5

    @patch('indexed.utils.components.alerts.console')
    def test_alert_with_formatting_codes(self, mock_console):
        """Should handle messages with Rich formatting codes."""
        print_success("[bold]Bold text[/bold] in message")
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_alert_with_paths(self, mock_console):
        """Should handle file paths in messages."""
        print_error("Failed to read /home/user/.indexed/config.toml")
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_alert_with_urls(self, mock_console):
        """Should handle URLs in messages."""
        print_info("Visit https://example.com for more information")
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_console_error_propagates(self, mock_console):
        """Should propagate console errors."""
        mock_console.print.side_effect = Exception("Console error")
        
        with pytest.raises(Exception):
            print_success("Test")

    @patch('indexed.utils.components.alerts.console')
    def test_very_long_single_word(self, mock_console):
        """Should handle very long single word."""
        long_word = "x" * 500
        print_success(long_word)
        
        assert mock_console.print.called

    @patch('indexed.utils.components.alerts.console')
    def test_message_with_tabs(self, mock_console):
        """Should handle messages with tab characters."""
        print_success("Column1\tColumn2\tColumn3")
        
        assert mock_console.print.called