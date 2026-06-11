"""MCP tool implementations for search operations.

Engine selection and search config are read from the server lifespan state via
:func:`indexed.mcp.config.get_lifespan_value`. Concrete service modules are
resolved through the engine router (``get_search_service`` / ``get_inspect_service``)
which lazily import the heavy v1/v2 stacks inside their function bodies.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastmcp import Context

from indexed_config.errors import IndexedError

from ..services.engine_router import get_inspect_service, get_search_service
from .config import (
    get_lifespan_value,
    resolve_engine_for_collection,
)
from .formatting import format_search_results_for_llm

DEFAULT_ENGINE = "v2"


def _normalize_v2_results(raw: dict) -> dict:
    """Convert v2 search output to v1-compatible display format for the LLM formatter."""
    if "collections" in raw:
        return {
            item["collectionName"]: {"results": item.get("results", [])}
            for item in raw["collections"]
        }
    return {raw["collectionName"]: {"results": raw.get("results", [])}}


def _search_config_from_ctx(ctx: Optional[Context]) -> Any:
    """Read the v1 search config from lifespan state, defaulting to config defaults."""
    from core.v1.config_models import CoreV1SearchConfig

    return get_lifespan_value(ctx, "search_config", CoreV1SearchConfig())


def _v2_search(
    query: str,
    *,
    collection: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a v2 search and normalize the result for the LLM formatter."""
    from core.v2.config import (
        CoreV2EmbeddingConfig,
        CoreV2SearchConfig,
        register_config as _register_v2_config,
    )
    from core.v2.services import SourceConfig
    from indexed_config import ConfigService

    from ..utils.storage_info import resolve_preferred_collections_path

    config_service = ConfigService.instance()
    _register_v2_config(config_service)  # idempotent — ensure specs registered
    provider = config_service.bind()
    search_cfg = provider.get(CoreV2SearchConfig)
    embed_cfg = provider.get(CoreV2EmbeddingConfig)

    collections_dir = resolve_preferred_collections_path()
    configs = (
        [SourceConfig(name=collection, type="localFiles", base_url_or_path="")]
        if collection
        else None
    )

    search_service = get_search_service("v2")
    raw = search_service.search(
        query,
        configs=configs,
        max_docs=search_cfg.max_docs,
        max_chunks=search_cfg.max_chunks,
        include_matched_chunks=search_cfg.include_matched_chunks,
        score_threshold=search_cfg.score_threshold,
        embed_model_name=embed_cfg.model_name,
        collections_dir=collections_dir,
    )
    return format_search_results_for_llm(_normalize_v2_results(raw), query)


def register_tools(mcp: Any) -> None:
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
        engine = str(get_lifespan_value(ctx, "engine", DEFAULT_ENGINE))

        try:
            if engine == "v2":
                return _v2_search(query)

            search_cfg = _search_config_from_ctx(ctx)
            search_service = get_search_service("v1")
            raw_results = search_service.search(
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
        except IndexedError as e:
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
        engine = resolve_engine_for_collection(collection, ctx, DEFAULT_ENGINE)

        try:
            if engine == "v2":
                return _v2_search(query, collection=collection)

            search_cfg = _search_config_from_ctx(ctx)
            inspect_service = get_inspect_service("v1")
            try:
                statuses = inspect_service.status([collection])
                if not statuses or not statuses[0].indexers:
                    return {
                        "error": f"Collection '{collection}' not found or has no indexers"
                    }
                default_indexer = statuses[0].indexers[0]
            except IndexedError:
                from core.v1.constants import DEFAULT_INDEXER

                default_indexer = DEFAULT_INDEXER

            from core.v1.engine.services import SourceConfig

            source_config = SourceConfig(
                name=collection,
                type="localFiles",
                base_url_or_path="",
                indexer=default_indexer,
            )

            search_service = get_search_service("v1")
            raw_results = search_service.search(
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
        except IndexedError as e:
            return {"error": str(e)}
