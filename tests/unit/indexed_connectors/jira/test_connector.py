"""Basic tests for Jira connectors."""

import os
from unittest.mock import patch
import pytest
from connectors.jira.connector import JiraConnector, JiraCloudConnector
from connectors.jira.schema import JiraConfig, JiraCloudConfig
from connectors.jira.jira_document_reader import JiraDocumentReader
from connectors.jira.async_jira_cloud_reader import AsyncJiraCloudDocumentReader


pytestmark = pytest.mark.connectors  # Mark all tests in this file as connector tests


def test_jira_connector_init():
    """Test JiraConnector initialization with token auth."""
    connector = JiraConnector(
        url="https://jira.example.com", query="project = TEST", token="test-token"
    )

    assert connector.connector_type == "jira"
    assert isinstance(connector.reader, JiraDocumentReader)
    assert (
        str(connector)
        == "JiraConnector(url='https://jira.example.com', query='project = TEST')"
    )


def test_jira_connector_basic_auth():
    """Test JiraConnector initialization with basic auth."""
    connector = JiraConnector(
        url="https://jira.example.com",
        query="project = TEST",
        login="user",
        password="pass",
    )

    assert isinstance(connector.reader, JiraDocumentReader)
    assert connector.connector_type == "jira"


def test_jira_connector_missing_auth():
    """Test JiraConnector raises error when no auth provided."""
    with pytest.raises(
        ValueError,
        match="Either 'token' or both 'login' and 'password' must be provided",
    ):
        JiraConnector(url="https://jira.example.com", query="project = TEST")


@patch.dict(os.environ, {"JIRA_TOKEN": "test-token"})
def test_jira_connector_from_config_dto():
    """Test JiraConnector creation from config DTO values."""
    config_dto = JiraConfig(
        url="https://jira.example.com",
        query="project = TEST",
        token="test-token",
    )

    # Use constructor directly (from_config requires full ConfigService)
    connector = JiraConnector(
        url=config_dto.url,
        query=config_dto.query,
        token=config_dto.get_token(),
    )
    assert isinstance(connector, JiraConnector)
    assert isinstance(connector.reader, JiraDocumentReader)
    assert connector.connector_type == "jira"


def test_jira_cloud_type_connector_init():
    """Test JiraCloudConnector initialization (jiraCloud type)."""
    connector = JiraCloudConnector(
        url="https://company.atlassian.net",
        query="project = TEST",
        email="test@example.com",
        api_token="test-token",
    )

    assert connector.connector_type == "jiraCloud"
    assert isinstance(connector.reader, AsyncJiraCloudDocumentReader)
    assert (
        str(connector)
        == "JiraCloudConnector(url='https://company.atlassian.net', query='project = TEST')"
    )


def test_jira_cloud_type_connector_from_config_dto():
    """Test JiraCloudConnector creation from config DTO values (jiraCloud type)."""
    config_dto = JiraCloudConfig(
        url="https://company.atlassian.net",
        query="project = TEST",
        email="test@example.com",
        api_token="test-token",
    )

    # Use constructor directly (from_config requires full ConfigService)
    connector = JiraCloudConnector(
        url=config_dto.url,
        query=config_dto.query,
        email=config_dto.get_email(),
        api_token=config_dto.get_api_token(),
    )
    assert isinstance(connector, JiraCloudConnector)
    assert isinstance(connector.reader, AsyncJiraCloudDocumentReader)
    assert connector.connector_type == "jiraCloud"


def test_jira_connector_config_spec():
    """Test JiraConnector.config_spec() returns correct specification."""
    spec = JiraConnector.config_spec()

    assert "url" in spec
    assert spec["url"]["required"] is True
    assert "query" in spec
    assert spec["query"]["required"] is True
    assert "token_env" in spec
    assert spec["token_env"]["secret"] is True


def test_jira_cloud_type_connector_config_spec():
    """Test JiraCloudConnector.config_spec() returns correct specification."""
    spec = JiraCloudConnector.config_spec()

    assert "url" in spec
    assert spec["url"]["required"] is True
    assert "query" in spec
    assert spec["query"]["required"] is True
    assert "email" in spec
    assert spec["email"]["required"] is True
    assert "api_token_env" in spec
    assert spec["api_token_env"]["secret"] is True
