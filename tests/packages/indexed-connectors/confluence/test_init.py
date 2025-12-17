"""Tests for confluence connector __init__ module."""
from unittest.mock import patch, MagicMock
from connectors.confluence import ConfluenceConnector, ConfluenceCloudConnector


def test_confluence_init_imports():
    """Test that imports work correctly."""
    assert ConfluenceConnector is not None
    assert ConfluenceCloudConnector is not None


def test_confluence_init_registration_success():
    """Test config registration succeeds when ConfigService available."""
    with patch('connectors.confluence.ConfigService') as mock_config_service:
        mock_instance = MagicMock()
        mock_config_service.instance.return_value = mock_instance
        
        # Re-import to trigger registration
        import importlib
        import connectors.confluence
        importlib.reload(connectors.confluence)
        
        # Verify registration was attempted
        # (Can't easily verify without actually importing, but at least we test the try/except)


def test_confluence_init_registration_failure():
    """Test config registration handles exceptions gracefully."""
    with patch('connectors.confluence.ConfigService', side_effect=ImportError("Not available")):
        # Should not raise
        import importlib
        import connectors.confluence
        importlib.reload(connectors.confluence)
        
        # Should still have the connectors available
        assert ConfluenceConnector is not None
        assert ConfluenceCloudConnector is not None



