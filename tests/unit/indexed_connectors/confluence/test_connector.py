"""Basic KISS tests for Confluence connectors."""

import os
from unittest.mock import patch
import pytest

from connectors.confluence.connector import (
    ConfluenceConnector,
    ConfluenceCloudConnector,
)
from connectors.confluence.schema import ConfluenceConfig, ConfluenceCloudConfig
from connectors.confluence.confluence_document_reader import ConfluenceDocumentReader
from connectors.confluence.async_confluence_cloud_reader import (
    AsyncConfluenceCloudDocumentReader,
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
def test_confluence_connector_from_config_dto_token():
    """Create ConfluenceConnector from config DTO values using token."""
    # Create config DTO to validate values, then use them with constructor
    config_dto = ConfluenceConfig(
        url="https://confluence.example.com",
        query="space = DEV",
        token="test-token",
    )

    # Use constructor directly (from_config requires full ConfigService)
    connector = ConfluenceConnector(
        url=config_dto.url,
        query=config_dto.query,
        token=config_dto.get_token(),
    )
    assert isinstance(connector, ConfluenceConnector)
    assert isinstance(connector.reader, ConfluenceDocumentReader)


def test_confluence_connector_from_config_dto_basic_auth():
    """Create ConfluenceConnector from config DTO values using basic auth."""
    config_dto = ConfluenceConfig(
        url="https://confluence.example.com",
        query="space = DEV",
        login="user",
        password="pass",
    )

    connector = ConfluenceConnector(
        url=config_dto.url,
        query=config_dto.query,
        login=config_dto.get_login(),
        password=config_dto.get_password(),
    )
    assert isinstance(connector, ConfluenceConnector)
    assert isinstance(connector.reader, ConfluenceDocumentReader)


def test_confluence_connector_read_all_comments_flag():
    """Test read_all_comments flag is properly passed through."""
    connector = ConfluenceConnector(
        url="https://confluence.example.com",
        query="type = page",
        token="test-token",
        read_all_comments=False,
    )

    assert connector.reader.read_all_comments is False


def test_confluence_connector_config_spec():
    """Test ConfluenceConnector.config_spec() returns correct specification."""
    spec = ConfluenceConnector.config_spec()

    assert "base_url" in spec
    assert spec["base_url"]["required"] is True
    assert "query" in spec
    assert spec["query"]["required"] is True
    assert "token_env" in spec
    assert spec["token_env"]["secret"] is True
    assert "read_all_comments" in spec
    assert spec["read_all_comments"]["default"] is True


# --- Confluence Cloud ---


def test_confluence_cloud_type_connector_init():
    """Instantiate ConfluenceCloudConnector with direct email+token (confluenceCloud type)."""
    connector = ConfluenceCloudConnector(
        url="https://company.atlassian.net",
        query="space = DEV",
        email="user@example.com",
        api_token="tok",
    )

    assert connector.connector_type == "confluenceCloud"
    assert isinstance(connector.reader, AsyncConfluenceCloudDocumentReader)
    assert (
        str(connector)
        == "ConfluenceCloudConnector(url='https://company.atlassian.net', query='space = DEV')"
    )


def test_confluence_cloud_type_connector_from_config_dto():
    """Create ConfluenceCloudConnector from config DTO values (confluenceCloud type)."""
    config_dto = ConfluenceCloudConfig(
        url="https://company.atlassian.net",
        query="space = DEV",
        email="user@example.com",
        api_token="test-token",
    )

    # Use constructor directly (from_config requires full ConfigService)
    connector = ConfluenceCloudConnector(
        url=config_dto.url,
        query=config_dto.query,
        email=config_dto.get_email(),
        api_token=config_dto.get_api_token(),
    )
    assert isinstance(connector, ConfluenceCloudConnector)
    assert isinstance(connector.reader, AsyncConfluenceCloudDocumentReader)


def test_confluence_cloud_type_connector_read_all_comments_flag():
    """Test read_all_comments flag is properly passed through (confluenceCloud type)."""
    connector = ConfluenceCloudConnector(
        url="https://company.atlassian.net",
        query="space = DEV",
        email="user@example.com",
        api_token="test-token",
        read_all_comments=False,
    )

    assert connector.reader.read_all_comments is False


def test_confluence_cloud_type_connector_config_spec():
    """Test ConfluenceCloudConnector.config_spec() returns correct specification."""
    spec = ConfluenceCloudConnector.config_spec()

    assert "base_url" in spec
    assert spec["base_url"]["required"] is True
    assert "query" in spec
    assert spec["query"]["required"] is True
    assert "email" in spec
    assert spec["email"]["required"] is True
    assert "api_token_env" in spec
    assert spec["api_token_env"]["secret"] is True
    assert "read_all_comments" in spec
    assert spec["read_all_comments"]["default"] is True
