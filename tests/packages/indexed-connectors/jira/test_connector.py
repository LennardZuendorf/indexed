"""Basic tests for Jira connectors."""
import os
from unittest.mock import MagicMock, Mock, patch
import pytest
from connectors.jira.connector import JiraConnector, JiraCloudConnector
from connectors.jira.jira_document_reader import JiraDocumentReader
from connectors.jira.jira_cloud_document_reader import JiraCloudDocumentReader


pytestmark = pytest.mark.connectors  # Mark all tests in this file as connector tests


def test_jira_connector_init():
    """Test JiraConnector initialization with token auth."""
    connector = JiraConnector(
        url="https://jira.example.com",
        query="project = TEST",
        token="test-token"
    )
    
    assert connector.connector_type == "jira"
    assert isinstance(connector.reader, JiraDocumentReader)
    assert str(connector) == "JiraConnector(url='https://jira.example.com', query='project = TEST')"


def test_jira_connector_basic_auth():
    """Test JiraConnector initialization with basic auth."""
    connector = JiraConnector(
        url="https://jira.example.com",
        query="project = TEST",
        login="user",
        password="pass"
    )
    
    assert isinstance(connector.reader, JiraDocumentReader)
    assert connector.connector_type == "jira"


def test_jira_connector_missing_auth():
    """Test JiraConnector raises error when no auth provided."""
    with pytest.raises(ValueError, match="Either 'token' or both 'login' and 'password' must be provided"):
        JiraConnector(
            url="https://jira.example.com",
            query="project = TEST"
        )


@patch.dict(os.environ, {"JIRA_TOKEN": "test-token"})
def test_jira_connector_from_config():
    """Test JiraConnector creation from config."""
    mock_config = MagicMock()
    mock_settings = MagicMock()
    mock_settings.test = Mock(spec=['base_url', 'query', 'token_env'])
    mock_settings.test.base_url = "https://jira.example.com"
    mock_settings.test.query = "project = TEST"
    mock_settings.test.token_env = "JIRA_TOKEN"
    mock_config.get.return_value = mock_settings
    
    connector = JiraConnector.from_config(mock_config, "test")
    assert isinstance(connector, JiraConnector)
    assert isinstance(connector.reader, JiraDocumentReader)
    os.environ.pop("JIRA_TOKEN")


def test_jira_cloud_connector_init():
    """Test JiraCloudConnector initialization."""
    connector = JiraCloudConnector(
        url="https://company.atlassian.net",
        query="project = TEST",
        email="test@example.com",
        api_token="test-token"
    )
    
    assert connector.connector_type == "jiraCloud"
    assert isinstance(connector.reader, JiraCloudDocumentReader)
    assert str(connector) == "JiraCloudConnector(url='https://company.atlassian.net', query='project = TEST')"


@patch.dict(os.environ, {"ATLASSIAN_TOKEN": "test-token"})
def test_jira_cloud_connector_from_config():
    """Test JiraCloudConnector creation from config."""
    mock_config = MagicMock()
    mock_settings = MagicMock()
    mock_settings.test = MagicMock(
        base_url="https://company.atlassian.net",
        query="project = TEST",
        email="test@example.com",
        api_token_env="ATLASSIAN_TOKEN"
    )
    mock_config.get.return_value = mock_settings
    
    connector = JiraCloudConnector.from_config(mock_config, "test")
    assert isinstance(connector, JiraCloudConnector)
    assert isinstance(connector.reader, JiraCloudDocumentReader)
    os.environ.pop("ATLASSIAN_TOKEN")


@patch.dict(os.environ, {"ATLASSIAN_TOKEN": "test-token"})
def test_jira_cloud_connector_missing_config():
    """Test JiraCloudConnector raises error with missing config."""
    mock_config = MagicMock()
    mock_settings = MagicMock()
    mock_settings.test = Mock(spec=['base_url', 'api_token_env'])
    mock_settings.test.base_url = "https://company.atlassian.net"
    mock_settings.test.api_token_env = "ATLASSIAN_TOKEN"
    # Missing email and jql
    mock_config.get.return_value = mock_settings
    
    with pytest.raises(ValueError, match="Jira Cloud config requires base_url, email, and query \\(jql\\)"):
        JiraCloudConnector.from_config(mock_config, "test")