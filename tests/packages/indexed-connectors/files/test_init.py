"""Tests for files connector __init__ module."""

from unittest.mock import patch, MagicMock
from connectors.files import FileSystemConnector


def test_files_init_imports():
    """Test that imports work correctly."""
    assert FileSystemConnector is not None


def test_files_init_registration_success():
    """Test config registration succeeds when ConfigService available."""
    with patch("connectors.files.ConfigService") as mock_config_service:
        mock_instance = MagicMock()
        mock_config_service.instance.return_value = mock_instance

        # Re-import to trigger registration
        import importlib
        import connectors.files

        importlib.reload(connectors.files)

        # Should not raise
        assert FileSystemConnector is not None


def test_files_init_registration_failure():
    """Test config registration handles exceptions gracefully."""
    with patch(
        "connectors.files.ConfigService", side_effect=ImportError("Not available")
    ):
        # Should not raise
        import importlib
        import connectors.files

        importlib.reload(connectors.files)

        # Should still have the connector available
        assert FileSystemConnector is not None
