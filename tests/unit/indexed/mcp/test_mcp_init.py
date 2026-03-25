"""Tests for indexed.mcp package lazy loading (__getattr__)."""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestMcpPackageLazyLoading:
    """Tests for the module-level __getattr__ in indexed/mcp/__init__.py."""

    def test_getattr_mcp_returns_mcp_object(self):
        """Accessing 'mcp' should trigger lazy import from server module."""
        import indexed.mcp as mcp_pkg

        mock_server = MagicMock()
        mock_server.mcp = "fake_mcp_object"

        with patch.dict(sys.modules, {"indexed.mcp.server": mock_server}):
            result = mcp_pkg.__getattr__("mcp")
            assert result == "fake_mcp_object"

    def test_getattr_main_returns_main_object(self):
        """Accessing 'main' should trigger lazy import from server module."""
        import indexed.mcp as mcp_pkg

        mock_server = MagicMock()
        mock_server.main = "fake_main_function"

        with patch.dict(sys.modules, {"indexed.mcp.server": mock_server}):
            result = mcp_pkg.__getattr__("main")
            assert result == "fake_main_function"

    def test_getattr_unknown_raises_attribute_error(self):
        """Accessing an unknown attribute should raise AttributeError."""
        import indexed.mcp as mcp_pkg

        with pytest.raises(AttributeError, match="has no attribute 'unknown_attr'"):
            mcp_pkg.__getattr__("unknown_attr")

    def test_known_exports_accessible(self):
        """app, run, dev, inspect, fastmcp, cli_main should be directly importable."""
        from indexed.mcp import app, run, dev, inspect, fastmcp, cli_main

        assert app is not None
        assert callable(run)
        assert callable(dev)
        assert callable(inspect)
        assert callable(fastmcp)
        assert callable(cli_main)
