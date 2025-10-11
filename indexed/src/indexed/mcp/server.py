"""Indexed MCP Server using FastMCP.

Provides search and inspect capabilities for document collections via MCP tools and resources.
"""

import os
from typing import Any, Dict, List
from fastmcp import FastMCP

# Import our service layer
from core.v1.engine.services import search as svc_search, status as svc_status, SourceConfig

# Create the FastMCP server instance
mcp = FastMCP("Indexed MCP Server")

# Configuration from environment variables
class MCPConfig:
    """Configuration for MCP server from environment variables."""
    
    def __init__(self):
        # Search configuration
        self.max_docs = int(os.getenv("INDEXED_MCP_MAX_DOCS", "10"))
        self.max_chunks = int(os.getenv("INDEXED_MCP_MAX_CHUNKS", "30"))  # Default: max_docs * 3
        self.include_full_text = os.getenv("INDEXED_MCP_INCLUDE_FULL_TEXT", "false").lower() == "true"
        self.include_all_chunks = os.getenv("INDEXED_MCP_INCLUDE_ALL_CHUNKS", "false").lower() == "true"
        self.include_matched_chunks = os.getenv("INDEXED_MCP_INCLUDE_MATCHED_CHUNKS", "false").lower() == "true"
        self.default_indexer = os.getenv("INDEXED_MCP_DEFAULT_INDEXER", "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2")
        
        # Inspect configuration
        self.include_index_size = os.getenv("INDEXED_MCP_INCLUDE_INDEX_SIZE", "false").lower() == "true"

# Global configuration instance
config = MCPConfig()


@mcp.tool()
def search(query: str) -> Dict[str, Any]:
    """
    Search across all available document collections using semantic similarity.
    
    Args:
        query: The search query text
        
    Returns:
        Dictionary with collection names as keys and search results as values
    """
    try:
        # Use auto-discovery mode (configs=None) to search all collections
        results = svc_search(
            query, 
            configs=None,
            max_docs=config.max_docs,
            max_chunks=config.max_chunks,
            include_full_text=config.include_full_text,
            include_all_chunks=config.include_all_chunks,
            include_matched_chunks=config.include_matched_chunks
        )
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def search_collection(collection: str, query: str) -> Dict[str, Any]:
    """
    Search within a specific document collection using semantic similarity.
    
    Uses the same environment variable configuration as the search tool.
    
    Args:
        collection: Name of the collection to search
        query: The search query text
        
    Returns:
        Dictionary with search results for the specified collection
    """
    try:
        # Get default indexer for the collection from inspect service
        try:
            statuses = svc_status([collection])
            if not statuses or not statuses[0].indexers:
                return {"error": f"Collection '{collection}' not found or has no indexers"}
            
            default_indexer = statuses[0].indexers[0]
        except Exception:
            # Fallback to configured default indexer
            default_indexer = config.default_indexer
        
        # Create SourceConfig for the specific collection
        source_config = SourceConfig(
            name=collection,
            type="localFiles",  # Type doesn't matter for search
            base_url_or_path="",  # Not used for search
            indexer=default_indexer,
        )
        
        results = svc_search(
            query, 
            configs=[source_config],
            max_docs=config.max_docs,
            max_chunks=config.max_chunks,
            include_full_text=config.include_full_text,
            include_all_chunks=config.include_all_chunks,
            include_matched_chunks=config.include_matched_chunks
        )
        return results
    except Exception as e:
        return {"error": str(e)}


@mcp.resource("resource://collections", name="CollectionsList", description="Return list of available collection names.")
def collections_list() -> List[str]:
    """Return list of available collection names."""
    try:
        statuses = svc_status()
        return [status.name for status in statuses]
    except Exception as e:
        return [f"error: {str(e)}"]


@mcp.resource("resource://collections/status", name="CollectionsStatusList", description="Return detailed status information for all collections.")
def collections_status_list() -> List[Dict[str, Any]]:
    """
    Return detailed status information for all collections.
    
    Configuration via environment variables:
    - INDEXED_MCP_INCLUDE_INDEX_SIZE: Include index size calculation (default: false)
    """
    try:
        statuses = svc_status(include_index_size=config.include_index_size)
        # Convert CollectionStatus objects to dictionaries
        return [
            {
                "name": s.name,
                "number_of_documents": s.number_of_documents,
                "number_of_chunks": s.number_of_chunks,
                "updated_time": s.updated_time,
                "last_modified_document_time": s.last_modified_document_time,
                "indexers": s.indexers,
                "index_size": s.index_size,
                "source_type": s.source_type,
                "relative_path": s.relative_path,
                "disk_size_bytes": s.disk_size_bytes,
            }
            for s in statuses
        ]
    except Exception as e:
        return [{"error": str(e)}]


@mcp.resource("resource://collections/{name}", name="CollectionStatus", description="Return detailed status information for a specific collection.")
def collection_status(name: str) -> Dict[str, Any]:
    """
    Return detailed status information for a specific collection.
    
    Uses the same environment variable configuration as collections_status_resource.
    """
    try:
        statuses = svc_status([name], include_index_size=config.include_index_size)
        if not statuses:
            return {"error": f"Collection '{name}' not found"}
        
        s = statuses[0]
        return {
            "name": s.name,
            "number_of_documents": s.number_of_documents,
            "number_of_chunks": s.number_of_chunks,
            "updated_time": s.updated_time,
            "last_modified_document_time": s.last_modified_document_time,
            "indexers": s.indexers,
            "index_size": s.index_size,
            "source_type": s.source_type,
            "relative_path": s.relative_path,
            "disk_size_bytes": s.disk_size_bytes,
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    """Main entry point for the MCP server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Server for indexed collections")
    parser.add_argument("--host", default="localhost", help="Host to bind to (default: localhost)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], 
                       help="Log level (default: INFO)")
    
    args = parser.parse_args()
    
    # Run the FastMCP server with parsed arguments
    mcp.run(host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
