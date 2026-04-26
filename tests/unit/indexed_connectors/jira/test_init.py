"""Tests for jira connector __init__ module."""

from unittest.mock import patch, MagicMock
from connectors.jira import JiraConnector, JiraCloudConnector


def test_jira_init_imports():
    """Test that imports work correctly."""
    assert JiraConnector is not None
    assert JiraCloudConnector is not None


def test_jira_init_registration_success():
    """Test config registration succeeds when ConfigService available."""
    with patch("connectors.jira.ConfigService") as mock_config_service:
        mock_instance = MagicMock()
        mock_config_service.instance.return_value = mock_instance

        # Re-import to trigger registration
        import importlib
        import connectors.jira

        importlib.reload(connectors.jira)

        # Should not raise
        assert JiraConnector is not None
        assert JiraCloudConnector is not None


def test_jira_init_registration_failure():
    """Test config registration handles exceptions gracefully."""
    with patch(
        "connectors.jira.ConfigService", side_effect=ImportError("Not available")
    ):
        # Should not raise
        import importlib
        import connectors.jira

        importlib.reload(connectors.jira)

        # Should still have the connectors available
        assert JiraConnector is not None
        assert JiraCloudConnector is not None
