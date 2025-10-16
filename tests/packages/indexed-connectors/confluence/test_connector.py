"""Basic KISS tests for Confluence connectors."""
import os
from unittest.mock import MagicMock, Mock, patch
import pytest

from connectors.confluence.connector import (
    ConfluenceConnector,
    ConfluenceCloudConnector,
)
from connectors.confluence.confluence_document_reader import ConfluenceDocumentReader
from connectors.confluence.confluence_cloud_document_reader import (
    ConfluenceCloudDocumentReader,
)


pytestmark = pytest.mark.connectors


# --- Confluence Server/DC ---

def test_confluence_connector_init_token():
    """Instantiate ConfluenceConnector with token auth."""
    connector = ConfluenceConnector(
        url="https://confluence.example.com",
        query="space = DEV",
        token="test-token",
    )

    assert connector.connector_type == "confluence"
    assert isinstance(connector.reader, ConfluenceDocumentReader)
    assert (
        str(connector)
        == "ConfluenceConnector(url='https://confluence.example.com', query='space = DEV')"
    )


def test_confluence_connector_basic_auth():
    """Instantiate ConfluenceConnector with basic auth."""
    connector = ConfluenceConnector(
        url="https://confluence.example.com",
        query="type = page",
        login="user",
        password="pass",
    )

    assert connector.connector_type == "confluence"
    assert isinstance(connector.reader, ConfluenceDocumentReader)


def test_confluence_connector_missing_auth():
    """Ensure ConfluenceConnector validates auth presence."""
    with pytest.raises(
        ValueError,
        match="Either 'token' or both 'login' and 'password' must be provided",
    ):
        ConfluenceConnector(url="https://confluence.example.com", query="space = DEV")


@patch.dict(os.environ, {"CONF_TOKEN": "test-token"})
def test_confluence_connector_from_config_token_env():
    """Create ConfluenceConnector from config using token_env."""
    mock_config = MagicMock()
    mock_settings = MagicMock()
    mock_settings.test = Mock(spec=["base_url", "query", "token_env"])
    mock_settings.test.base_url = "https://confluence.example.com"
    mock_settings.test.query = "space = DEV"
    mock_settings.test.token_env = "CONF_TOKEN"
    mock_config.get.return_value = mock_settings

    connector = ConfluenceConnector.from_config(mock_config, "test")
    assert isinstance(connector, ConfluenceConnector)
    assert isinstance(connector.reader, ConfluenceDocumentReader)


def test_confluence_connector_from_config_missing_fields():
    """Missing base_url or query should raise a clear error."""
    mock_config = MagicMock()
    mock_settings = MagicMock()
    mock_settings.test = Mock(spec=["base_url"])  # missing query
    mock_settings.test.base_url = "https://confluence.example.com"
    mock_config.get.return_value = mock_settings

    with pytest.raises(
        ValueError, match=r"Confluence \(Server/DC\) config requires base_url and query"
    ):
        ConfluenceConnector.from_config(mock_config, "test")


def test_confluence_connector_from_config_legacy_comment_flag():
    """Legacy readOnlyFirstLevelComments should map to read_all_comments=False."""
    mock_config = MagicMock()
    mock_settings = MagicMock()
    # Provide minimal required config
    section = MagicMock()
    section.base_url = "https://confluence.example.com"
    section.query = "type = page"
    section.token_env = "CONF_TOKEN"
    section.readOnlyFirstLevelComments = True
    mock_settings.test = section
    mock_config.get.return_value = mock_settings
    with patch.dict(os.environ, {"CONF_TOKEN": "tok"}):
        connector = ConfluenceConnector.from_config(mock_config, "test")
        assert connector.reader.read_all_comments is False


# --- Confluence Cloud ---

def test_confluence_cloud_connector_init():
    """Instantiate ConfluenceCloudConnector with direct email+token."""
    connector = ConfluenceCloudConnector(
        url="https://company.atlassian.net",
        query="space = DEV",
        email="user@example.com",
        api_token="tok",
    )

    assert connector.connector_type == "confluenceCloud"
    assert isinstance(connector.reader, ConfluenceCloudDocumentReader)
    assert (
        str(connector)
        == "ConfluenceCloudConnector(url='https://company.atlassian.net', query='space = DEV')"
    )


@patch.dict(os.environ, {"ATLASSIAN_TOKEN": "tok", "ATLASSIAN_EMAIL": "user@example.com"})
def test_confluence_cloud_connector_from_config_envs():
    """Create ConfluenceCloudConnector from config with env fallbacks."""
    mock_config = MagicMock()
    mock_settings = MagicMock()
    mock_settings.test = Mock(
        spec=["base_url", "query", "email", "api_token_env", "read_all_comments"],
    )
    mock_settings.test.base_url = "https://company.atlassian.net"
    mock_settings.test.query = "space = DEV"
    mock_settings.test.email = None  # force env fallback
    mock_settings.test.api_token_env = "ATLASSIAN_TOKEN"
    mock_config.get.return_value = mock_settings

    connector = ConfluenceCloudConnector.from_config(mock_config, "test")
    assert isinstance(connector, ConfluenceCloudConnector)
    assert isinstance(connector.reader, ConfluenceCloudDocumentReader)


def test_confluence_cloud_connector_missing_config():
    """Ensure missing required fields raise a clear error."""
    mock_config = MagicMock()
    mock_settings = MagicMock()
    mock_settings.test = Mock(spec=["base_url"])  # missing email and query
    mock_settings.test.base_url = "https://company.atlassian.net/wiki"
    mock_config.get.return_value = mock_settings

    with pytest.raises(
        ValueError,
        match="Confluence Cloud config requires base_url, email, and query \(cql\)",
    ):
        ConfluenceCloudConnector.from_config(mock_config, "test")


def test_confluence_cloud_connector_missing_token():
    """Missing ATLASSIAN_TOKEN and api_token_env resolution should error."""
    mock_config = MagicMock()
    mock_settings = MagicMock()
    mock_settings.test = Mock(
        spec=["base_url", "query", "email", "api_token_env", "read_all_comments"],
    )
    mock_settings.test.base_url = "https://company.atlassian.net"
    mock_settings.test.query = "space = DEV"
    mock_settings.test.email = "user@example.com"
    mock_settings.test.api_token_env = "ATLASSIAN_TOKEN"
    mock_config.get.return_value = mock_settings

    with patch.dict(os.environ, {}, clear=True):
        # Ensure fallback secret resolver returns None as well
        with patch("connectors.confluence.connector._get_env_var", return_value=None):
            with pytest.raises(
                ValueError,
                match=(
                    "Missing Atlassian API token. Set ATLASSIAN_TOKEN or the configured api_token_env."
                ),
            ):
                ConfluenceCloudConnector.from_config(mock_config, "test")
