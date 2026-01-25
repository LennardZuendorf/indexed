"""Indexed MCP Server using FastMCP.

Provides search and inspect capabilities for document collections via MCP tools and resources.
Uses FastMCP 2.13+ features including server lifespan and response caching middleware.
"""

# Suppress SWIG deprecation warnings from faiss (upstream issue, not fixed yet)
# Must be done before any faiss imports occur
import argparse
import warnings

warnings.filterwarnings("ignore", message="builtin type Swig.*")

from contextlib import asynccontextmanager  # noqa: E402
from typing import Any, AsyncIterator, Dict, List, Optional, TypedDict  # noqa: E402

from fastmcp import FastMCP  # noqa: E402
from fastmcp.server.middleware.caching import ResponseCachingMiddleware  # noqa: E402

try:
    from fastmcp import Context  # noqa: E402
except ImportError:
    # Fallback for older FastMCP versions
    Context = None  # type: ignore

# Import ConfigService for configuration
from core.v1.config_models import CoreV1SearchConfig, MCPConfig  # noqa: E402
from core.v1.engine.services import (  # noqa: E402
    SourceConfig,
    search as svc_search,
    status as svc_status,
)
from indexed_config import ConfigService  # noqa: E402


class LifespanState(TypedDict):
    """Type definition for lifespan state returned to tools/resources."""

    mcp_config: MCPConfig
    search_config: CoreV1SearchConfig


def _get_mcp_config() -> MCPConfig:
    """
    Load the MCP configuration from the application's configuration service.

    Attempts to read the MCPConfig from the configuration hierarchy (defaults -> global TOML -> workspace TOML -> environment); if the configuration service is unavailable or an error occurs, returns a default MCPConfig instance.

    Returns:
        MCPConfig: The resolved MCP configuration, or a default MCPConfig on failure.
    """
    try:
        config_service = ConfigService.instance()
        config_service.register(MCPConfig, path="mcp")
        provider = config_service.bind()
        return provider.get(MCPConfig)
    except Exception:
        # Fallback to defaults if ConfigService unavailable
        return MCPConfig()


def _get_search_config() -> CoreV1SearchConfig:
    """
    Load the search configuration from the configuration service, falling back to defaults if unavailable.

    Returns:
        CoreV1SearchConfig: Configuration values from the "core.v1.search" path, or a default CoreV1SearchConfig if retrieval fails.
    """
    try:
        config_service = ConfigService.instance()
        config_service.register(CoreV1SearchConfig, path="core.v1.search")
        provider = config_service.bind()
        return provider.get(CoreV1SearchConfig)
    except Exception:
        # Fallback to defaults if ConfigService unavailable
        return CoreV1SearchConfig()


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[LifespanState]:
    """Server lifespan context manager for configuration initialization.

    This runs once when the server starts (not per-client session).
    Initializes configuration and yields it for use by tools/resources.

    Args:
        server: The FastMCP server instance

    Yields:
        LifespanState with mcp_config and search_config
    """
    # Initialize configuration at server startup
    mcp_config = _get_mcp_config()
    search_config = _get_search_config()

    yield {"mcp_config": mcp_config, "search_config": search_config}


# Create the FastMCP server instance with lifespan
mcp = FastMCP("Indexed MCP Server", lifespan=lifespan)

# Add response caching middleware for expensive search operations
# This caches tool and resource call results with TTL-based expiration
mcp.add_middleware(ResponseCachingMiddleware())


# Legacy config accessors for backward compatibility and non-lifespan contexts
_mcp_config: Optional[MCPConfig] = None
_search_config: Optional[CoreV1SearchConfig] = None


def get_mcp_config() -> MCPConfig:
    """
    Return the cached MCP configuration, initializing it from the configuration service if not already loaded (used as a fallback outside lifespan).

    Returns:
        MCPConfig: The cached MCP configuration instance.
    """
    global _mcp_config
    if _mcp_config is None:
        _mcp_config = _get_mcp_config()
    return _mcp_config


def get_search_config() -> CoreV1SearchConfig:
    """
    Return the cached CoreV1SearchConfig, loading it from the configuration service on first access.

    Returns:
        CoreV1SearchConfig: The active search configuration used by the server.
    """
    global _search_config
    if _search_config is None:
        _search_config = _get_search_config()
    return _search_config


def _format_search_results_for_llm(
    raw_results: Dict[str, Any], query: str
) -> Dict[str, Any]:
    """
    Transform raw search results into an LLM-optimized format.

    Flattens nested structures, extracts content directly, and provides
    clear context for each result with relevance ranking.

    Args:
        raw_results: Raw search results from search service
        query: Original search query

    Returns:
        LLM-friendly dictionary with ranked results and clear metadata
    """
    formatted = {
        "query": query,
        "total_collections_searched": 0,
        "total_documents_found": 0,
        "total_chunks_found": 0,
        "results": [],
    }

    # Collect all chunks from all collections with metadata
    all_chunks = []

    for collection_name, collection_data in raw_results.items():
        if isinstance(collection_data, dict) and "error" in collection_data:
            continue

        formatted["total_collections_searched"] += 1

        if not isinstance(collection_data, dict) or "results" not in collection_data:
            continue

        documents = collection_data.get("results", [])
        formatted["total_documents_found"] += len(documents)

        for doc in documents:
            doc_id = doc.get("id", "unknown")
            doc_url = doc.get("url", "")
            matched_chunks = doc.get("matchedChunks", [])

            for chunk_data in matched_chunks:
                chunk_number = chunk_data.get("chunkNumber", 0)
                score = chunk_data.get("score", 999.0)

                # Extract actual text content from nested structure
                content_text = ""
                if "content" in chunk_data:
                    content = chunk_data["content"]
                    if isinstance(content, dict) and "indexedData" in content:
                        content_text = content["indexedData"]
                    elif isinstance(content, str):
                        content_text = content

                # Only include chunks with actual content
                if content_text:
                    all_chunks.append(
                        {
                            "rank": 0,  # Will be set after sorting
                            "relevance_score": score,
                            "collection": collection_name,
                            "document_id": doc_id,
                            "document_url": doc_url,
                            "chunk_number": chunk_number,
                            "text": content_text,
                        }
                    )

    # Sort by relevance (lower score = more relevant for L2 distance)
    all_chunks.sort(key=lambda x: x["relevance_score"])

    # Assign ranks and add to results
    for idx, chunk in enumerate(all_chunks, 1):
        chunk["rank"] = idx
        formatted["results"].append(chunk)

    formatted["total_chunks_found"] = len(all_chunks)

    return formatted


@mcp.tool
def search(query: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
    """
    Search all available document collections for semantically similar content to the provided query.

    Returns results in an LLM-optimized format with flat structure and direct text access.
    Results are ranked by relevance with the most relevant chunks first.

    Parameters:
        query (str): The search query text.
        ctx (Optional[Context]): FastMCP Context (optional, for accessing lifespan state).

    Returns:
        dict: LLM-friendly search results with structure:
            - query: The original search query
            - total_collections_searched: Number of collections searched
            - total_documents_found: Number of documents with matches
            - total_chunks_found: Total number of matching text chunks
            - results: List of ranked results, each containing:
                - rank: Relevance ranking (1 = most relevant)
                - relevance_score: Similarity score (lower = more similar)
                - collection: Collection name
                - document_id: Document identifier
                - document_url: Source document URL
                - chunk_number: Chunk position in document
                - text: Actual text content
    """
    # Try to get config from lifespan state, fallback to cached getter
    if ctx is not None and hasattr(ctx, "fastmcp_context"):
        try:
            lifespan_state = getattr(ctx.fastmcp_context, "lifespan_context", None)
            if lifespan_state:
                search_cfg = lifespan_state.get("search_config")
            else:
                search_cfg = get_search_config()
        except (AttributeError, TypeError):
            search_cfg = get_search_config()
    else:
        search_cfg = get_search_config()

    try:
        # Use auto-discovery mode (configs=None) to search all collections
        raw_results = svc_search(
            query,
            configs=None,
            max_docs=search_cfg.max_docs,
            max_chunks=search_cfg.max_chunks,
            score_threshold=search_cfg.score_threshold,
            include_full_text=search_cfg.include_full_text,
            include_all_chunks=search_cfg.include_all_chunks,
            include_matched_chunks=search_cfg.include_matched_chunks,
        )

        # Transform to LLM-friendly format
        return _format_search_results_for_llm(raw_results, query)
    except Exception as e:
        return {"error": str(e)}


@mcp.tool
def search_collection(
    collection: str, query: str, ctx: Optional[Context] = None
) -> Dict[str, Any]:
    """
    Search within a specific document collection using semantic similarity.

    Returns results in the same LLM-optimized format as the general search tool.

    Args:
        collection: Name of the collection to search
        query: The search query text
        ctx: FastMCP Context (optional, for accessing lifespan state)

    Returns:
        dict: LLM-friendly search results with the same structure as search() tool
    """
    # Try to get config from lifespan state, fallback to cached getter
    if ctx is not None and hasattr(ctx, "fastmcp_context"):
        try:
            lifespan_state = getattr(ctx.fastmcp_context, "lifespan_context", None)
            if lifespan_state:
                search_cfg = lifespan_state.get("search_config")
            else:
                search_cfg = get_search_config()
        except (AttributeError, TypeError):
            search_cfg = get_search_config()
    else:
        search_cfg = get_search_config()

    try:
        # Get default indexer for the collection from inspect service
        try:
            statuses = svc_status([collection])
            if not statuses or not statuses[0].indexers:
                return {
                    "error": f"Collection '{collection}' not found or has no indexers"
                }

            default_indexer = statuses[0].indexers[0]
        except Exception:
            # Fallback to default indexer
            from core.v1.constants import DEFAULT_INDEXER

            default_indexer = DEFAULT_INDEXER

        # Create SourceConfig for the specific collection
        source_config = SourceConfig(
            name=collection,
            type="localFiles",  # Type doesn't matter for search
            base_url_or_path="",  # Not used for search
            indexer=default_indexer,
        )

        raw_results = svc_search(
            query,
            configs=[source_config],
            max_docs=search_cfg.max_docs,
            max_chunks=search_cfg.max_chunks,
            score_threshold=search_cfg.score_threshold,
            include_full_text=search_cfg.include_full_text,
            include_all_chunks=search_cfg.include_all_chunks,
            include_matched_chunks=search_cfg.include_matched_chunks,
        )

        # Transform to LLM-friendly format
        return _format_search_results_for_llm(raw_results, query)
    except Exception as e:
        return {"error": str(e)}


@mcp.resource(
    "resource://collections/{_all}",
    name="CollectionsList",
    description="Return list of available collection names.",
)
def collections_list(_all: str = "all") -> List[str]:
    """Return list of available collection names."""
    try:
        statuses = svc_status()
        return [status.name for status in statuses]
    except Exception as e:
        return [f"error: {str(e)}"]


@mcp.resource(
    "resource://collections/status/{_all}",
    name="CollectionsStatusList",
    description="Return detailed status information for all collections.",
)
def collections_status_list(
    _all: str = "all", ctx: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Return detailed status information for all collections.

    Each item is a mapping of collection attributes (name, document and chunk counts, timestamps, indexer names, index size, source type, relative path, and disk usage). The `include_index_size` flag from the MCP configuration controls whether index size is populated.

    Parameters:
        ctx (Optional[Context]): FastMCP Context (optional, for accessing lifespan state).

    Returns:
        List[Dict[str, Any]]: A list of collection status dictionaries with keys:
            - name: collection name
            - number_of_documents: total documents in the collection
            - number_of_chunks: total chunks derived from documents
            - updated_time: last index update time (as provided by the status object)
            - last_modified_document_time: timestamp of the most recently modified source document
            - indexers: list of indexer names associated with the collection
            - index_size: size of the index (may be omitted or null if not requested)
            - source_type: type of the collection source
            - relative_path: source relative path
            - disk_size_bytes: disk usage in bytes
        On error, returns a single-item list containing {"error": "<error message>"}.
    """
    # Try to get config from lifespan state, fallback to cached getter
    if ctx is not None and hasattr(ctx, "fastmcp_context"):
        try:
            lifespan_state = getattr(ctx.fastmcp_context, "lifespan_context", None)
            if lifespan_state:
                mcp_cfg = lifespan_state.get("mcp_config")
            else:
                mcp_cfg = get_mcp_config()
        except (AttributeError, TypeError):
            mcp_cfg = get_mcp_config()
    else:
        mcp_cfg = get_mcp_config()

    try:
        statuses = svc_status(include_index_size=mcp_cfg.include_index_size)
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


@mcp.resource(
    "resource://collections/{name}",
    name="CollectionStatus",
    description="Return detailed status information for a specific collection.",
)
def collection_status(name: str, ctx: Optional[Any] = None) -> Dict[str, Any]:
    """
    Get detailed status information for a named collection.

    Uses the same configuration as collections_status_list.

    Parameters:
        name (str): Collection name to query.
        ctx (Optional[Context]): FastMCP Context (optional, for accessing lifespan state).

    Returns:
        dict: A mapping with the collection's status fields:
            - name: collection name
            - number_of_documents: total documents in the collection
            - number_of_chunks: total chunks derived from documents
            - updated_time: last time the collection status was updated
            - last_modified_document_time: timestamp of the most recently modified document
            - indexers: list of configured indexers for the collection
            - index_size: size of the index for the collection (when available)
            - source_type: type of the source (e.g., "localFiles")
            - relative_path: collection's relative path
            - disk_size_bytes: on-disk size in bytes
        If the collection is not found or an error occurs, returns {'error': <message>}.
    """
    # Try to get config from lifespan state, fallback to cached getter
    if ctx is not None and hasattr(ctx, "fastmcp_context"):
        try:
            lifespan_state = getattr(ctx.fastmcp_context, "lifespan_context", None)
            if lifespan_state:
                mcp_cfg = lifespan_state.get("mcp_config")
            else:
                mcp_cfg = get_mcp_config()
        except (AttributeError, TypeError):
            mcp_cfg = get_mcp_config()
    else:
        mcp_cfg = get_mcp_config()

    try:
        statuses = svc_status([name], include_index_size=mcp_cfg.include_index_size)
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

    # Get MCP config for defaults
    mcp_cfg = get_mcp_config()

    parser = argparse.ArgumentParser(description="MCP Server for indexed collections")
    parser.add_argument(
        "--host",
        default=mcp_cfg.host,
        help=f"Host to bind to (default: {mcp_cfg.host})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=mcp_cfg.port,
        help=f"Port to bind to (default: {mcp_cfg.port})",
    )
    parser.add_argument(
        "--log-level",
        default=mcp_cfg.log_level,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Log level (default: {mcp_cfg.log_level})",
    )

    args = parser.parse_args()

    # Run the FastMCP server with parsed arguments
    mcp.run(host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
