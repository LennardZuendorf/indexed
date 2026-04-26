"""MCP tool implementations for search operations."""

from typing import Any, Callable, Dict, Optional

from fastmcp import Context

from core.v1.engine.services import (
    SourceConfig,
    search as svc_search,
    status as svc_status,
)

from .config import resolve_config as _resolve_config
from .formatting import format_search_results_for_llm


def register_tools(mcp: Any, get_search_config: Callable[[], Any]) -> None:
    """Register search tools on the FastMCP instance."""

    @mcp.tool
    def search(query: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
        """Search all available document collections for semantically similar content.

        Returns results in an LLM-optimized format with flat structure and direct text access.
        Results are ranked by relevance with the most relevant chunks first.

        Parameters:
            query (str): The search query text.
            ctx (Optional[Context]): FastMCP Context (optional, for accessing lifespan state).

        Returns:
            dict: LLM-friendly search results with ranked results containing
                rank, relevance_score, collection, document_id, document_url,
                chunk_number, and text fields.
        """
        search_cfg = _resolve_config(ctx, "search_config", get_search_config)

        try:
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
            return format_search_results_for_llm(raw_results, query)
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool
    def search_collection(
        collection: str,
        query: str,
        ctx: Optional[Context] = None,
    ) -> Dict[str, Any]:
        """Search within a specific document collection using semantic similarity.

        Returns results in the same LLM-optimized format as the general search tool.

        Args:
            collection: Name of the collection to search
            query: The search query text
            ctx: FastMCP Context (optional, for accessing lifespan state)

        Returns:
            dict: LLM-friendly search results with the same structure as search() tool
        """
        search_cfg = _resolve_config(ctx, "search_config", get_search_config)

        try:
            try:
                statuses = svc_status([collection])
                if not statuses or not statuses[0].indexers:
                    return {
                        "error": f"Collection '{collection}' not found or has no indexers"
                    }
                default_indexer = statuses[0].indexers[0]
            except Exception:
                from core.v1.constants import DEFAULT_INDEXER

                default_indexer = DEFAULT_INDEXER

            source_config = SourceConfig(
                name=collection,
                type="localFiles",
                base_url_or_path="",
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
            return format_search_results_for_llm(raw_results, query)
        except Exception as e:
            return {"error": str(e)}
