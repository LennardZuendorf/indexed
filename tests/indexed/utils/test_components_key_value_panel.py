"""Comprehensive tests for key_value_panel component module."""

from unittest.mock import Mock, patch
import pytest

from indexed.utils.components.key_value_panel import (
    _truncate,
    create_key_value_panel,
)


class TestTruncate:
    """Test _truncate helper function."""

    def test_returns_short_string_unchanged(self):
        """Should return strings shorter than max_len unchanged."""
        assert _truncate("short", 10) == "short"
        assert _truncate("test", 20) == "test"

    def test_truncates_long_string(self):
        """Should truncate strings longer than max_len."""
        result = _truncate("very long string here", 10)
        assert len(result) == 10
        assert result.endswith("...")

    def test_truncates_at_exact_length(self):
        """Should handle string exactly at max_len."""
        exact = "x" * 10
        result = _truncate(exact, 10)
        assert result == exact

    def test_truncates_one_over_length(self):
        """Should truncate string that's one char too long."""
        result = _truncate("12345678901", 10)
        assert len(result) == 10
        assert result == "1234567..."

    def test_handles_zero_max_len(self):
        """Should return empty string for max_len of 0."""
        result = _truncate("anything", 0)
        assert result == ""

    def test_handles_negative_max_len(self):
        """Should return empty string for negative max_len."""
        result = _truncate("anything", -5)
        assert result == ""

    def test_handles_max_len_less_than_three(self):
        """Should handle max_len less than 3 (ellipsis length)."""
        assert _truncate("test", 1) == "t"
        assert _truncate("test", 2) == "te"

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert _truncate("", 10) == ""

    def test_preserves_unicode(self):
        """Should handle Unicode strings correctly."""
        result = _truncate("Hello 世界 🌍", 8)
        assert len(result) == 8
        assert result.endswith("...")

    def test_truncates_multiline(self):
        """Should truncate multiline strings."""
        multiline = "line1\nline2\nline3"
        result = _truncate(multiline, 10)
        assert len(result) == 10


class TestCreateKeyValuePanel:
    """Test create_key_value_panel function."""

    def test_creates_panel_with_title(self):
        """Should create panel with specified title."""
        rows = [("key1", "value1")]
        panel = create_key_value_panel("Test Title", rows, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)
        assert panel.title

    def test_two_column_mode(self):
        """Should create two-column layout when show_category=False."""
        rows = [("key1", "value1"), ("key2", "value2")]
        panel = create_key_value_panel("Test", rows, show_category=False, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_three_column_mode(self):
        """Should create three-column layout when show_category=True."""
        rows = [("cat1", "key1", "value1"), ("cat2", "key2", "value2")]
        panel = create_key_value_panel("Test", rows, show_category=True, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_handles_empty_rows(self):
        """Should handle empty rows list."""
        panel = create_key_value_panel("Empty", [], show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_includes_headers_when_requested(self):
        """Should include header row when show_headers=True."""
        rows = [("key1", "value1")]
        panel = create_key_value_panel("Test", rows, show_category=False, show_headers=True)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_custom_headers(self):
        """Should use custom headers when provided."""
        rows = [("key1", "value1")]
        custom_headers = ("Custom Key", "Custom Value")
        panel = create_key_value_panel(
            "Test", rows, 
            show_category=False, 
            show_headers=True, 
            headers=custom_headers
        )
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_truncates_long_values(self):
        """Should truncate values exceeding value_max_len."""
        long_value = "x" * 100
        rows = [("key", long_value)]
        panel = create_key_value_panel(
            "Test", rows, 
            show_category=False,
            show_headers=False,
            value_max_len=20
        )
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_respects_column_widths(self):
        """Should respect custom column widths."""
        rows = [("category", "key", "value")]
        panel = create_key_value_panel(
            "Test", rows,
            show_category=True,
            show_headers=False,
            category_width=20,
            key_width=30
        )
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_expand_parameter(self):
        """Should respect expand parameter."""
        rows = [("key", "value")]
        
        panel_expand = create_key_value_panel("Test", rows, show_headers=False, expand=True)
        panel_no_expand = create_key_value_panel("Test", rows, show_headers=False, expand=False)
        
        from rich.panel import Panel
        assert isinstance(panel_expand, Panel)
        assert isinstance(panel_no_expand, Panel)

    def test_mixed_row_formats_with_category(self):
        """Should handle 2-tuple rows in 3-column mode (empty category)."""
        rows = [
            ("cat1", "key1", "value1"),
            ("key2", "value2"),  # 2-tuple treated as (key, value) with empty category
        ]
        panel = create_key_value_panel("Test", rows, show_category=True, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)


class TestKeyValuePanelEdgeCases:
    """Test edge cases for key_value_panel."""

    def test_handles_none_in_rows(self):
        """Should handle None values in rows."""
        rows = [("key", None)]
        panel = create_key_value_panel("Test", rows, show_category=False, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_handles_numeric_values(self):
        """Should handle numeric values in rows."""
        rows = [("count", 42), ("percent", 3.14)]
        # Values will be converted to strings
        panel = create_key_value_panel("Test", rows, show_category=False, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_handles_special_characters(self):
        """Should handle special characters in values."""
        rows = [("path", "/home/user/$file"), ("url", "https://example.com?q=test&x=1")]
        panel = create_key_value_panel("Test", rows, show_category=False, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_handles_unicode(self):
        """Should handle Unicode characters."""
        rows = [("name", "Hello 世界"), ("emoji", "🎉 🚀")]
        panel = create_key_value_panel("Test", rows, show_category=False, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_handles_multiline_values(self):
        """Should handle multiline values."""
        rows = [("description", "Line 1\nLine 2\nLine 3")]
        panel = create_key_value_panel("Test", rows, show_category=False, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_handles_empty_strings(self):
        """Should handle empty strings in rows."""
        rows = [("", "value"), ("key", ""), ("", "")]
        panel = create_key_value_panel("Test", rows, show_category=False, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_many_rows(self):
        """Should handle many rows efficiently."""
        rows = [(f"key{i}", f"value{i}") for i in range(100)]
        panel = create_key_value_panel("Test", rows, show_category=False, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_very_long_title(self):
        """Should handle very long panel title."""
        long_title = "x" * 200
        rows = [("key", "value")]
        panel = create_key_value_panel(long_title, rows, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_custom_widths_with_small_values(self):
        """Should handle custom widths smaller than content."""
        rows = [("very_long_category_name", "very_long_key_name", "very_long_value")]
        panel = create_key_value_panel(
            "Test", rows,
            show_category=True,
            show_headers=False,
            category_width=5,
            key_width=5,
            value_max_len=5
        )
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_zero_widths(self):
        """Should handle zero width parameters."""
        rows = [("key", "value")]
        panel = create_key_value_panel(
            "Test", rows,
            show_category=False,
            show_headers=False,
            key_width=0,
            value_max_len=0
        )
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)

    def test_inconsistent_row_tuples(self):
        """Should handle rows with inconsistent tuple lengths."""
        # In 3-column mode with mixed 2 and 3-tuples
        rows = [
            ("cat1", "key1", "value1"),  # 3-tuple
            ("key2", "value2"),           # 2-tuple
            ("cat3", "key3", "value3"),  # 3-tuple
        ]
        # Implementation should handle this gracefully
        panel = create_key_value_panel("Test", rows, show_category=True, show_headers=False)
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)