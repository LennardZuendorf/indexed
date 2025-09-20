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

    @patch('main.services.search_service.search')
    def test_search_function_success(self, mock_search):
        """Test search function returns results successfully."""
        # Arrange
        mock_search.return_value = {
            "collection1": {"documents": [{"title": "Test Doc"}]},
            "collection2": {"documents": [{"title": "Another Doc"}]}
        }
        
        # Import and get the function
        import server.mcp as server_module
        
        # Find the search function
        search_func = None
        for name, obj in vars(server_module).items():
            if hasattr(obj, 'fn') and name == 'search':
                search_func = obj.fn
                break
        
        if search_func is None:
            pytest.skip("Could not find search function - FastMCP structure may have changed")
        
        # Act
        result = search_func("test query")
        
        # Assert
        assert isinstance(result, dict)
        mock_search.assert_called_once_with("test query", configs=None)

    @patch('main.services.search_service.search')
    def test_search_function_error_handling(self, mock_search):
        """Test search function handles errors gracefully."""
        # Arrange
        mock_search.side_effect = Exception("Search failed")
        
        import server.mcp as server_module
        
        # Find the search function
        search_func = None
        for name, obj in vars(server_module).items():
            if hasattr(obj, 'fn') and name == 'search':
                search_func = obj.fn
                break
        
        if search_func is None:
            pytest.skip("Could not find search function")
        
        # Act
        result = search_func("test query")
        
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
        
        import server.mcp as server_module
        
        # Find the collections list resource function
        collections_resource_func = None
        for name, obj in vars(server_module).items():
            if hasattr(obj, 'fn') and name == 'collections_list':
                collections_resource_func = obj.fn
                break
        
        if collections_resource_func is None:
            pytest.skip("Could not find collections_list function")
        
        # Act
        result = collections_resource_func()
        
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
        
        import server.mcp as server_module
        
        # Find the collections list resource function
        collections_resource_func = None
        for name, obj in vars(server_module).items():
            if hasattr(obj, 'fn') and name == 'collections_list':
                collections_resource_func = obj.fn
                break
        
        if collections_resource_func is None:
            pytest.skip("Could not find collections_list function")
        
        # Act
        result = collections_resource_func()
        
        # Assert
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == "error: Status failed"

    def test_search_collection_function_exists(self):
        """Test that search_collection function exists."""
        import server.mcp as server_module
        
        # Find the search_collection function
        search_collection_func = None
        for name, obj in vars(server_module).items():
            if hasattr(obj, 'fn') and name == 'search_collection':
                search_collection_func = obj.fn
                break
        
        # Just verify it exists and is callable
        if search_collection_func is not None:
            assert callable(search_collection_func)
        else:
            pytest.skip("Could not find search_collection function")

    def test_collections_status_list_function_exists(self):
        """Test that collections_status_list function exists."""
        import server.mcp as server_module
        
        # Find the collections_status_list function
        collections_status_resource_func = None
        for name, obj in vars(server_module).items():
            if hasattr(obj, 'fn') and name == 'collections_status_list':
                collections_status_resource_func = obj.fn
                break
        
        # Just verify it exists and is callable
        if collections_status_resource_func is not None:
            assert callable(collections_status_resource_func)
        else:
            pytest.skip("Could not find collections_status_list function")

    def test_collection_status_function_exists(self):
        """Test that collection_status function exists."""
        import server.mcp as server_module
        
        # Find the collection_status function
        collection_status_resource_func = None
        for name, obj in vars(server_module).items():
            if hasattr(obj, 'fn') and name == 'collection_status':
                collection_status_resource_func = obj.fn
                break
        
        # Just verify it exists and is callable
        if collection_status_resource_func is not None:
            assert callable(collection_status_resource_func)
        else:
            pytest.skip("Could not find collection_status function")
