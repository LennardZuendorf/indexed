"""Tests for the MCP server tools and resources."""

import pytest
from unittest.mock import patch
from main.services.models import CollectionStatus


class TestMCPServerIntegration:
    """Integration tests for MCP server."""

    def test_server_instance_exists(self):
        """Test that the MCP server instance is created."""
        from server.mcp import mcp
        
        assert mcp is not None
        assert mcp.name == "Indexed MCP Server"

    def test_main_function_exists(self):
        """Test that the main function exists and is callable."""
        from server.mcp import main
        
        assert callable(main)

    def test_server_imports_successfully(self):
        """Test that the server module imports without errors."""
        try:
            import server.mcp  # noqa: F401
            assert True
        except ImportError as e:
            pytest.fail(f"Server module failed to import: {e}")


class TestMCPServerFunctions:
    """Test the underlying functions used by MCP tools and resources."""

    @patch('server.mcp.svc_search')
    def test_search_function_success(self, mock_search):
        """Test search function returns results successfully."""
        # Arrange
        mock_search.return_value = {
            "collection1": {"documents": [{"title": "Test Doc"}]},
            "collection2": {"documents": [{"title": "Another Doc"}]}
        }
        
        # Import the wrapped function from the server module and get the underlying function
        from server.mcp import search
        search_fn = search.fn
        
        # Act
        result = search_fn("test query")
        
        # Assert
        assert isinstance(result, dict)
        # Check that the mock was called with the expected arguments
        # Note: the actual call includes all the config parameters from MCPConfig
        assert mock_search.called
        call_args = mock_search.call_args
        assert call_args[0][0] == "test query"  # First positional arg is query
        assert call_args[1]["configs"] is None  # configs should be None for auto-discovery

    @patch('server.mcp.svc_search')
    def test_search_function_error_handling(self, mock_search):
        """Test search function handles errors gracefully."""
        # Arrange
        mock_search.side_effect = Exception("Search failed")
        
        # Import the wrapped function from the server module and get the underlying function
        from server.mcp import search
        search_fn = search.fn
        
        # Act
        result = search_fn("test query")
        
        # Assert
        assert "error" in result
        assert result["error"] == "Search failed"

    @patch('server.mcp.svc_status')
    def test_collections_resource_function_success(self, mock_status):
        """Test collections resource function returns collection names."""
        # Arrange
        mock_status.return_value = [
            CollectionStatus(
                name="collection1",
                number_of_documents=5,
                number_of_chunks=15,
                updated_time="2024-01-01T00:00:00Z",
                last_modified_document_time="2024-01-01T00:00:00Z",
                indexers=["test_indexer"],
                index_size=None,
                source_type="files",
                relative_path="./data/collections/collection1",
                disk_size_bytes=1024
            ),
            CollectionStatus(
                name="collection2",
                number_of_documents=3,
                number_of_chunks=9,
                updated_time="2024-01-01T00:00:00Z",
                last_modified_document_time="2024-01-01T00:00:00Z",
                indexers=["test_indexer"],
                index_size=None,
                source_type="jira",
                relative_path="./data/collections/collection2",
                disk_size_bytes=512
            )
        ]
        
        # Import the wrapped function from the server module and get the underlying function
        from server.mcp import collections_list
        collections_list_fn = collections_list.fn
        
        # Act
        result = collections_list_fn()
        
        # Assert
        assert isinstance(result, list)
        assert len(result) == 2
        assert "collection1" in result
        assert "collection2" in result
        mock_status.assert_called_once_with()

    @patch('server.mcp.svc_status')
    def test_collections_resource_function_error_handling(self, mock_status):
        """Test collections resource function handles errors gracefully."""
        # Arrange
        mock_status.side_effect = Exception("Status failed")
        
        # Import the wrapped function from the server module and get the underlying function
        from server.mcp import collections_list
        collections_list_fn = collections_list.fn
        
        # Act
        result = collections_list_fn()
        
        # Assert
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == "error: Status failed"

    def test_search_collection_function_exists(self):
        """Test that search_collection function exists."""
        from server.mcp import search_collection
        
        # The wrapped object has the actual function in .fn
        assert hasattr(search_collection, 'fn')
        assert callable(search_collection.fn)

    def test_collections_status_resource_function_exists(self):
        """Test that collections_status_resource function exists."""
        from server.mcp import collections_status_list
        
        # The wrapped object has the actual function in .fn
        assert hasattr(collections_status_list, 'fn')
        assert callable(collections_status_list.fn)

    def test_collection_status_resource_function_exists(self):
        """Test that collection_status_resource function exists."""
        from server.mcp import collection_status
        
        # The wrapped object has the actual function in .fn
        assert hasattr(collection_status, 'fn')
        assert callable(collection_status.fn)
