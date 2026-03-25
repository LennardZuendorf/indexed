"""Tests for indexed error hierarchy."""

import pytest
from indexed_config.errors import IndexedError
from indexed.errors import CLIError, MCPError


class TestErrorHierarchy:
    """Test that error classes form the correct hierarchy."""

    def test_cli_error_is_indexed_error(self):
        """CLIError should be a subclass of IndexedError."""
        assert issubclass(CLIError, IndexedError)

    def test_mcp_error_is_indexed_error(self):
        """MCPError should be a subclass of IndexedError."""
        assert issubclass(MCPError, IndexedError)

    def test_cli_error_is_exception(self):
        """CLIError should ultimately be an Exception."""
        assert issubclass(CLIError, Exception)

    def test_mcp_error_is_exception(self):
        """MCPError should ultimately be an Exception."""
        assert issubclass(MCPError, Exception)


class TestRaiseAndCatch:
    """Test raising and catching each error type."""

    def test_raise_cli_error(self):
        """Should be able to raise and catch CLIError."""
        with pytest.raises(CLIError):
            raise CLIError("cli failure")

    def test_raise_mcp_error(self):
        """Should be able to raise and catch MCPError."""
        with pytest.raises(MCPError):
            raise MCPError("mcp failure")

    def test_catch_cli_error_as_indexed_error(self):
        """CLIError should be catchable as IndexedError."""
        with pytest.raises(IndexedError):
            raise CLIError("cli failure")

    def test_catch_mcp_error_as_indexed_error(self):
        """MCPError should be catchable as IndexedError."""
        with pytest.raises(IndexedError):
            raise MCPError("mcp failure")

    def test_cli_error_message(self):
        """CLIError should preserve the message."""
        err = CLIError("test message")
        assert str(err) == "test message"

    def test_mcp_error_message(self):
        """MCPError should preserve the message."""
        err = MCPError("test message")
        assert str(err) == "test message"
