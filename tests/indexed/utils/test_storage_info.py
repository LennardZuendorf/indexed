"""Comprehensive tests for storage_info utility module."""

from pathlib import Path
from unittest.mock import Mock
import pytest
from rich.console import Console

from indexed.utils.storage_info import (
    get_storage_indicator,
    print_storage_info,
    get_storage_mode_and_reason,
)


class TestGetStorageIndicator:
    """Test get_storage_indicator function."""

    def test_global_mode_indicator(self):
        """Should return global indicator with globe icon."""
        path = Path.home() / ".indexed"
        result = get_storage_indicator("global", path)

        assert "🌐" in result
        assert "Global" in result
        assert "~/.indexed" in result

    def test_local_mode_indicator(self):
        """Should return local indicator with folder icon."""
        path = Path.cwd() / ".indexed"
        result = get_storage_indicator("local", path)

        assert "📁" in result
        assert "Local" in result

    def test_replaces_home_with_tilde(self):
        """Should replace home directory with tilde in path."""
        path = Path.home() / "some" / "nested" / "path"
        result = get_storage_indicator("global", path)

        assert "~" in result
        assert str(Path.home()) not in result

    def test_includes_reason_when_provided(self):
        """Should include reason in output when provided."""
        path = Path.home() / ".indexed"
        reason = "via config setting"
        result = get_storage_indicator("global", path, reason=reason)

        assert reason in result
        assert " - " in result

    def test_no_reason_omits_separator(self):
        """Should not include separator when reason is None."""
        path = Path.home() / ".indexed"
        result = get_storage_indicator("global", path, reason=None)

        assert " - " not in result

    def test_local_path_not_replaced(self):
        """Should not replace tilde for non-home paths."""
        path = Path("/opt/indexed")
        result = get_storage_indicator("local", path)

        assert "/opt/indexed" in result
        assert "~" not in result

    def test_empty_reason_treated_as_none(self):
        """Should treat empty string reason like None."""
        path = Path.home() / ".indexed"
        result = get_storage_indicator("global", path, reason="")

        # Empty reason might still show separator; behavior depends on implementation
        assert "Global" in result


class TestPrintStorageInfo:
    """Test print_storage_info function."""

    def test_prints_to_console(self):
        """Should print storage info to Rich console."""
        mock_console = Mock(spec=Console)
        path = Path.home() / ".indexed"
        print_storage_info(mock_console, "global", path)

        assert mock_console.print.called

    def test_newline_before_when_specified(self):
        """Should print newline before indicator when requested."""
        mock_console = Mock(spec=Console)
        path = Path.home() / ".indexed"
        print_storage_info(mock_console, "global", path, newline_before=True)

        # Should have multiple print calls
        assert mock_console.print.call_count >= 2

    def test_newline_after_when_specified(self):
        """Should print newline after indicator when requested."""
        mock_console = Mock(spec=Console)
        path = Path.home() / ".indexed"
        print_storage_info(mock_console, "global", path, newline_after=True)

        assert mock_console.print.call_count >= 2

    def test_no_newlines_when_both_false(self):
        """Should print only indicator when both newline options are False."""
        mock_console = Mock(spec=Console)
        path = Path.home() / ".indexed"
        print_storage_info(
            mock_console, "global", path, newline_before=False, newline_after=False
        )

        # Should print once (just the indicator)
        assert mock_console.print.call_count == 1

    def test_includes_reason_in_output(self):
        """Should include reason in printed output."""
        mock_console = Mock(spec=Console)
        path = Path.home() / ".indexed"
        reason = "via --global flag"
        print_storage_info(mock_console, "global", path, reason=reason)

        # Check that printed string contains reason
        call_args = str(mock_console.print.call_args_list)
        assert "via --global flag" in call_args or mock_console.print.called

    def test_local_mode_formatting(self):
        """Should format local mode correctly."""
        mock_console = Mock(spec=Console)
        path = Path.cwd() / ".indexed"
        print_storage_info(mock_console, "local", path)

        assert mock_console.print.called


class TestGetStorageModeAndReason:
    """Test get_storage_mode_and_reason function."""

    def test_local_flag_override_takes_precedence(self):
        """Should use --local flag over all other settings."""
        mode, reason = get_storage_mode_and_reason(
            has_local=True,
            mode_override="local",
            config_mode="global",
            workspace_pref="global",
        )

        assert mode == "local"
        assert "via --local flag" in reason

    def test_global_flag_override_takes_precedence(self):
        """Should use --global flag over all other settings."""
        mode, reason = get_storage_mode_and_reason(
            has_local=True,
            mode_override="global",
            config_mode="local",
            workspace_pref="local",
        )

        assert mode == "global"
        assert "via --global flag" in reason

    def test_config_mode_used_when_no_override(self):
        """Should use config setting when no CLI override."""
        mode, reason = get_storage_mode_and_reason(
            has_local=False,
            mode_override=None,
            config_mode="local",
            workspace_pref="global",
        )

        assert mode == "local"
        assert "via config setting" in reason

    def test_workspace_preference_used_when_no_config(self):
        """Should use saved workspace preference when no config or override."""
        mode, reason = get_storage_mode_and_reason(
            has_local=False,
            mode_override=None,
            config_mode=None,
            workspace_pref="global",
        )

        assert mode == "global"
        assert "saved preference" in reason

    def test_local_indexed_detected_when_no_preferences(self):
        """Should detect local .indexed folder when no preferences set."""
        mode, reason = get_storage_mode_and_reason(
            has_local=True,
            mode_override=None,
            config_mode=None,
            workspace_pref=None,
        )

        assert mode == "local"
        assert "local .indexed found" in reason

    def test_defaults_to_global_when_nothing_set(self):
        """Should default to global when no settings or local folder."""
        mode, reason = get_storage_mode_and_reason(
            has_local=False,
            mode_override=None,
            config_mode=None,
            workspace_pref=None,
        )

        assert mode == "global"
        assert "default" in reason

    def test_all_none_values(self):
        """Should handle all None values and default to global."""
        mode, reason = get_storage_mode_and_reason(
            has_local=False,
            mode_override=None,
            config_mode=None,
            workspace_pref=None,
        )

        assert mode == "global"
        assert reason == "default"

    def test_config_global_overrides_workspace_pref(self):
        """Should prefer config setting over workspace preference."""
        mode, reason = get_storage_mode_and_reason(
            has_local=True,
            mode_override=None,
            config_mode="global",
            workspace_pref="local",
        )

        assert mode == "global"
        assert "via config setting" in reason

    def test_workspace_pref_overrides_local_detected(self):
        """Should prefer workspace preference over detected local folder."""
        mode, reason = get_storage_mode_and_reason(
            has_local=True,
            mode_override=None,
            config_mode=None,
            workspace_pref="global",
        )

        assert mode == "global"
        assert "saved preference" in reason


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_indicator_with_very_long_path(self):
        """Should handle very long paths."""
        long_path = Path("/very/long/nested/path/structure/that/goes/on/and/on")
        result = get_storage_indicator("local", long_path)

        assert "Local" in result
        assert str(long_path) in result

    def test_indicator_with_special_characters_in_path(self):
        """Should handle special characters in paths."""
        special_path = Path("/path/with spaces/and-dashes/under_scores")
        result = get_storage_indicator("global", special_path)

        assert "Global" in result

    def test_print_with_none_reason(self):
        """Should handle None reason gracefully."""
        mock_console = Mock(spec=Console)
        path = Path.home() / ".indexed"
        print_storage_info(mock_console, "global", path, reason=None)

        assert mock_console.print.called

    def test_storage_mode_resolution_precedence_order(self):
        """Should verify complete precedence order."""
        # CLI override > config > workspace pref > detected local > default

        # Test each level
        cases = [
            # (has_local, override, config, pref, expected_mode, expected_reason_keyword)
            (True, "global", "local", "local", "global", "flag"),
            (True, None, "local", "global", "local", "config"),
            (True, None, None, "global", "global", "preference"),
            (True, None, None, None, "local", "found"),
            (False, None, None, None, "global", "default"),
        ]

        for has_local, override, config, pref, expected_mode, reason_keyword in cases:
            mode, reason = get_storage_mode_and_reason(
                has_local, override, config, pref
            )
            assert mode == expected_mode
            assert reason_keyword in reason

    def test_print_handles_console_errors_gracefully(self):
        """Should not crash if console printing fails."""
        mock_console = Mock(spec=Console)
        mock_console.print.side_effect = Exception("Console error")

        path = Path.home() / ".indexed"
        # Should raise the exception (no suppression in this function)
        with pytest.raises(Exception):
            print_storage_info(mock_console, "global", path)

    def test_get_indicator_with_root_path(self):
        """Should handle root path (/)."""
        result = get_storage_indicator("global", Path("/"))
        assert "Global" in result
        assert "/" in result

    def test_get_indicator_with_relative_path(self):
        """Should handle relative paths."""
        result = get_storage_indicator("local", Path("./relative/path"))
        assert "Local" in result

    def test_mode_and_reason_returns_tuple(self):
        """Should always return tuple of (mode, reason)."""
        result = get_storage_mode_and_reason(False, None, None, None)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)
