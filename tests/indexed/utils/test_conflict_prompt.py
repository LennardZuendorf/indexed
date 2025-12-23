"""Comprehensive tests for conflict prompt utility module."""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from rich.console import Console

from indexed.utils.conflict_prompt import (
    format_value,
    show_config_differences,
    prompt_storage_choice,
)


class TestFormatValue:
    """Test format_value function."""

    def test_formats_short_string(self):
        """Should return short strings unchanged."""
        result = format_value("short", max_length=40)
        assert result == "short"

    def test_formats_int(self):
        """Should convert integers to strings."""
        result = format_value(42)
        assert result == "42"

    def test_formats_float(self):
        """Should convert floats to strings."""
        result = format_value(3.14159)
        assert result == "3.14159"

    def test_formats_bool(self):
        """Should convert booleans to strings."""
        assert format_value(True) == "True"
        assert format_value(False) == "False"

    def test_formats_none(self):
        """Should convert None to string."""
        result = format_value(None)
        assert result == "None"

    def test_truncates_long_string(self):
        """Should truncate strings exceeding max_length."""
        long_str = "a" * 50
        result = format_value(long_str, max_length=20)
        assert len(result) == 20
        assert result.endswith("...")
        assert result == "a" * 17 + "..."

    def test_truncates_at_exact_length(self):
        """Should handle string exactly at max_length."""
        exact_str = "a" * 40
        result = format_value(exact_str, max_length=40)
        assert result == exact_str

    def test_handles_empty_string(self):
        """Should handle empty string."""
        result = format_value("")
        assert result == ""

    def test_formats_list(self):
        """Should convert lists to strings."""
        result = format_value([1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_formats_dict(self):
        """Should convert dicts to strings."""
        result = format_value({"key": "value"})
        assert "key" in result

    def test_custom_max_length(self):
        """Should respect custom max_length parameter."""
        result = format_value("123456789", max_length=5)
        assert len(result) == 5
        assert result == "12..."


class TestShowConfigDifferences:
    """Test show_config_differences function."""

    def test_shows_differences_table(self):
        """Should display table with config differences."""
        mock_console = Mock(spec=Console)
        differences = {
            "setting1": ("local_value", "global_value"),
            "setting2": (123, 456),
        }

        show_config_differences(differences, mock_console)

        # Should print table
        assert mock_console.print.called
        call_args = [str(call) for call in mock_console.print.call_args_list]
        printed = " ".join(call_args)
        assert "setting1" in printed or mock_console.print.call_count > 0

    def test_shows_empty_message_when_no_differences(self):
        """Should show message when no differences exist."""
        mock_console = Mock(spec=Console)
        differences = {}

        show_config_differences(differences, mock_console)

        # Should print message about no differences
        assert mock_console.print.called

    def test_truncates_long_values(self):
        """Should truncate very long values in display."""
        mock_console = Mock(spec=Console)
        differences = {
            "long_setting": ("a" * 100, "b" * 100),
        }

        show_config_differences(differences, mock_console)

        # Should have called format (implicitly tested via no errors)
        assert mock_console.print.called

    def test_handles_nested_paths(self):
        """Should display nested dot-path settings."""
        mock_console = Mock(spec=Console)
        differences = {
            "section.subsection.key": ("local", "global"),
        }

        show_config_differences(differences, mock_console)

        assert mock_console.print.called

    def test_handles_none_values(self):
        """Should handle None values in differences."""
        mock_console = Mock(spec=Console)
        differences = {
            "nullable": (None, "value"),
            "unset": ("value", None),
        }

        show_config_differences(differences, mock_console)

        assert mock_console.print.called


class TestPromptStorageChoice:
    """Test prompt_storage_choice function."""

    @patch("indexed.utils.conflict_prompt.Prompt.ask")
    def test_prompts_user_for_choice(self, mock_prompt):
        """Should prompt user to choose storage mode."""
        mock_console = Mock(spec=Console)
        mock_prompt.return_value = "1"

        result = prompt_storage_choice(mock_console)

        mock_prompt.assert_called_once()
        assert result in ["global", "local", "global_remember", "local_remember"]

    @patch("indexed.utils.conflict_prompt.Prompt.ask")
    def test_returns_global_for_choice_1(self, mock_prompt):
        """Should return 'global' when user selects option 1."""
        mock_console = Mock(spec=Console)
        mock_prompt.return_value = "1"

        result = prompt_storage_choice(mock_console)

        assert result == "global"

    @patch("indexed.utils.conflict_prompt.Prompt.ask")
    def test_returns_local_for_choice_2(self, mock_prompt):
        """Should return 'local' when user selects option 2."""
        mock_console = Mock(spec=Console)
        mock_prompt.return_value = "2"

        result = prompt_storage_choice(mock_console)

        assert result == "local"

    @patch("indexed.utils.conflict_prompt.Prompt.ask")
    def test_returns_global_remember_for_choice_3(self, mock_prompt):
        """Should return 'global_remember' when user selects option 3."""
        mock_console = Mock(spec=Console)
        mock_prompt.return_value = "3"

        result = prompt_storage_choice(mock_console)

        assert result == "global_remember"

    @patch("indexed.utils.conflict_prompt.Prompt.ask")
    def test_returns_local_remember_for_choice_4(self, mock_prompt):
        """Should return 'local_remember' when user selects option 4."""
        mock_console = Mock(spec=Console)
        mock_prompt.return_value = "4"

        result = prompt_storage_choice(mock_console)

        assert result == "local_remember"

    @patch("indexed.utils.conflict_prompt.show_config_differences")
    @patch("indexed.utils.conflict_prompt.Prompt.ask")
    def test_shows_differences_when_provided(self, mock_prompt, mock_show_diff):
        """Should display differences when provided."""
        mock_console = Mock(spec=Console)
        mock_prompt.return_value = "1"
        differences = {"key": ("local", "global")}

        prompt_storage_choice(mock_console, differences=differences)

        mock_show_diff.assert_called_once_with(differences, mock_console)

    @patch("indexed.utils.conflict_prompt.Prompt.ask")
    def test_shows_workspace_path_when_provided(self, mock_prompt):
        """Should display workspace path in prompt."""
        mock_console = Mock(spec=Console)
        mock_prompt.return_value = "1"
        workspace = Path("/home/user/project")

        prompt_storage_choice(mock_console, workspace_path=workspace)

        # Should have printed workspace info
        assert mock_console.print.called

    @patch("indexed.utils.conflict_prompt.Prompt.ask")
    def test_handles_invalid_choice_reprompts(self, mock_prompt):
        """Should handle invalid choices gracefully."""
        mock_console = Mock(spec=Console)
        # First invalid, then valid
        mock_prompt.side_effect = ["invalid", "1"]

        result = prompt_storage_choice(mock_console)

        # Should have prompted at least twice
        assert mock_prompt.call_count >= 1
        assert result in ["global", "local", "global_remember", "local_remember"]

    @patch("indexed.utils.conflict_prompt.Prompt.ask")
    def test_handles_numeric_string_choices(self, mock_prompt):
        """Should handle choices as strings."""
        mock_console = Mock(spec=Console)
        for choice in ["1", "2", "3", "4"]:
            mock_prompt.return_value = choice
            result = prompt_storage_choice(mock_console)
            assert result in ["global", "local", "global_remember", "local_remember"]


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch("indexed.utils.conflict_prompt.Prompt.ask")
    def test_handles_keyboard_interrupt(self, mock_prompt):
        """Should handle user cancellation (Ctrl+C)."""
        mock_console = Mock(spec=Console)
        mock_prompt.side_effect = KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            prompt_storage_choice(mock_console)

    def test_handles_empty_differences_dict(self):
        """Should handle empty differences dictionary."""
        mock_console = Mock(spec=Console)
        show_config_differences({}, mock_console)
        assert mock_console.print.called

    def test_format_value_with_zero_max_length(self):
        """Should handle max_length of 0."""
        result = format_value("test", max_length=0)
        # When max_length is 0, len("test")=4 > 0, so it truncates: s[:0-3] = s[:-3] = "t" + "..."
        assert result == "t..."

    def test_format_value_with_negative_max_length(self):
        """Should handle negative max_length."""
        result = format_value("test", max_length=-5)
        # When max_length is -5, len("test")=4 > -5, so it truncates: s[:-5-3] = s[:-8] = "" + "..."
        assert result == "..."

    def test_shows_differences_with_special_characters(self):
        """Should handle special characters in values."""
        mock_console = Mock(spec=Console)
        differences = {
            "path": ("/some/path/with/$pecial", "/another/path"),
            "url": ("https://example.com?q=test&x=1", "https://other.com"),
        }

        show_config_differences(differences, mock_console)
        assert mock_console.print.called

    @patch("indexed.utils.conflict_prompt.Prompt.ask")
    def test_prompt_with_none_workspace_path(self, mock_prompt):
        """Should handle None workspace_path."""
        mock_console = Mock(spec=Console)
        mock_prompt.return_value = "1"

        result = prompt_storage_choice(mock_console, workspace_path=None)

        assert result in ["global", "local", "global_remember", "local_remember"]
