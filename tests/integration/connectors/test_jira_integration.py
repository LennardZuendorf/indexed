"""Integration tests for Jira connector.

Tests the JiraConnector with mocked API server,
verifying API interaction, issue reading, and conversion.
"""

import pytest
from connectors.jira import JiraConnector


@pytest.mark.integration
@pytest.mark.api
def test_jira_connector_basic(mock_jira_server):
    """Test Jira connector with mocked API server."""
    connector = JiraConnector(
        url=f"http://localhost:{mock_jira_server.port}",
        query="project = TEST",
        token="test-token"
    )
    
    # Verify connector type
    assert connector.connector_type == "jira"
    
    # Test document reading
    documents = list(connector.reader.read_all_documents())
    
    assert len(documents) > 0, "Should retrieve issues from mock server"
    
    # Verify first document structure (documents are dicts from Jira API)
    first_doc = documents[0]
    assert isinstance(first_doc, dict)
    assert 'id' in first_doc
    assert 'key' in first_doc
    assert first_doc['id'] == "10001"
    assert first_doc['key'] == "TEST-1"


@pytest.mark.integration
@pytest.mark.api
def test_jira_connector_conversion(mock_jira_server):
    """Test Jira connector document conversion."""
    connector = JiraConnector(
        url=f"http://localhost:{mock_jira_server.port}",
        query="project = TEST",
        token="test-token"
    )
    
    # Read documents
    documents = list(connector.reader.read_all_documents())
    assert len(documents) > 0
    
    # Test conversion (converter returns list of converted documents)
    converted = connector.converter.convert(documents[0])
    
    assert isinstance(converted, list)
    assert len(converted) > 0, "Should produce at least one converted document"
    
    # Verify converted document structure
    first_converted = converted[0]
    assert 'id' in first_converted
    assert 'text' in first_converted
    assert 'chunks' in first_converted
    assert len(first_converted['chunks']) > 0


@pytest.mark.integration
@pytest.mark.api
def test_jira_connector_with_token_auth(mock_jira_server):
    """Test Jira connector with token authentication."""
    connector = JiraConnector(
        url=f"http://localhost:{mock_jira_server.port}",
        query="assignee = currentUser()",
        token="test-bearer-token"
    )
    
    # Verify connector configuration
    assert connector._url == f"http://localhost:{mock_jira_server.port}"
    assert connector._query == "assignee = currentUser()"
    
    # Test document reading
    documents = list(connector.reader.read_all_documents())
    assert len(documents) > 0


@pytest.mark.integration
@pytest.mark.api
def test_jira_connector_with_basic_auth(mock_jira_server):
    """Test Jira connector with username/password authentication."""
    connector = JiraConnector(
        url=f"http://localhost:{mock_jira_server.port}",
        query="project = TEST",
        login="test-user",
        password="test-password"
    )
    
    # Verify connector configuration
    assert connector._url == f"http://localhost:{mock_jira_server.port}"
    
    # Test document reading
    documents = list(connector.reader.read_all_documents())
    assert len(documents) > 0


@pytest.mark.integration
def test_jira_connector_requires_auth():
    """Test that Jira connector requires authentication."""
    with pytest.raises(ValueError, match="Either 'token' or both 'login' and 'password' must be provided"):
        JiraConnector(
            url="http://localhost:8080",
            query="project = TEST"
        )

