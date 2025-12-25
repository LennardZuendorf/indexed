"""Integration tests for Confluence connector.

Tests the ConfluenceConnector with mocked API server,
verifying API interaction, document reading, and conversion.
"""

import pytest
from connectors.confluence import ConfluenceConnector


@pytest.mark.unit_api
def test_confluence_connector_basic(mock_confluence_server):
    """Test Confluence connector with mocked API server."""
    connector = ConfluenceConnector(
        url=f"http://localhost:{mock_confluence_server.port}",
        query="space = TEST",
        token="test-token",
    )

    # Verify connector type
    assert connector.connector_type == "confluence"

    # Test document reading
    documents = list(connector.reader.read_all_documents())

    assert len(documents) > 0, "Should retrieve documents from mock server"

    # Verify first document structure (documents are dicts with 'page' and 'comments' keys)
    first_doc = documents[0]
    assert isinstance(first_doc, dict)
    assert "page" in first_doc
    assert "comments" in first_doc
    assert first_doc["page"]["id"] == "123"


@pytest.mark.unit_api
def test_confluence_connector_conversion(mock_confluence_server):
    """Test Confluence connector document conversion."""
    connector = ConfluenceConnector(
        url=f"http://localhost:{mock_confluence_server.port}",
        query="space = TEST",
        token="test-token",
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
    assert "id" in first_converted
    assert "text" in first_converted
    assert "chunks" in first_converted
    assert len(first_converted["chunks"]) > 0


@pytest.mark.unit_api
def test_confluence_connector_with_comments(mock_confluence_server):
    """Test Confluence connector with comment reading enabled."""
    connector = ConfluenceConnector(
        url=f"http://localhost:{mock_confluence_server.port}",
        query="space = TEST",
        token="test-token",
        read_all_comments=True,
    )

    # Verify connector is configured correctly
    assert connector._read_all_comments is True

    # Test document reading still works
    documents = list(connector.reader.read_all_documents())
    assert len(documents) > 0


@pytest.mark.unit_api
def test_confluence_connector_without_all_comments(mock_confluence_server):
    """Test Confluence connector with only top-level comments."""
    connector = ConfluenceConnector(
        url=f"http://localhost:{mock_confluence_server.port}",
        query="space = TEST",
        token="test-token",
        read_all_comments=False,
    )

    # Verify connector is configured correctly
    assert connector._read_all_comments is False

    # Test document reading still works
    documents = list(connector.reader.read_all_documents())
    assert len(documents) > 0
