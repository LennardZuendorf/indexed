"""Tests for key_value_panel component module.

Only the behavioral ``_truncate`` logic is exercised here. The rendering-only
tests (asserting ``isinstance(panel, Panel)`` for ``create_key_value_panel``)
were pure chrome and have been removed; the panel builder is UI presentation
covered by system-level UI consistency tests.
"""

from indexed.cli.utils.components.key_value_panel import _truncate


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
