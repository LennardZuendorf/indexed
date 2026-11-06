"""MCP tool implementations for search operations."""

from typing import Any, Callable, Dict, List, Optional, get_args

from fastmcp import Context
from loguru import logger

from indexed.core.engine import (
    SourceConfig,
    search as svc_search,
    status as svc_status,
)

from indexed.config.errors import IndexedError

from indexed.cli.errors import MCPError, mcp_error_envelope
from .collection_errors import unresolvable_collection_error
from .config import resolve_cli_context, resolve_config as _resolve_config
from .formatting import format_search_results_for_llm

# Derived once from the SourceConfig Literal so the set stays in sync with the model.
_ALLOWED_SOURCE_TYPES: frozenset[str] = frozenset(
    get_args(SourceConfig.model_fields["type"].annotation)
)


def _run_search(
    query: str,
    configs: Optional[List[Any]],
    search_cfg: Any,
    collections_path: str,
    *,
    changed_since: Optional[str] = None,
    git_provenance: Optional[bool] = None,
    git_line_blame: Optional[bool] = None,
    git_rerank: Optional[bool] = None,
) -> Dict[str, Any]:
    """Execute a search and return formatted results or a graceful error envelope."""
    # Only the requested git keys are splatted: all default to None (off), and
    # an omitted option must not reach the engine as an explicit override. An
    # omitted ``git_provenance``/``git_line_blame`` means "configured default",
    # exactly like the CLI (``[core.v1.search] git_provenance``) — the CLI/MCP
    # parity invariant of ``_load_search_config`` applies to both keys (#279).
    git_kwargs: Dict[str, Any] = {}
    if changed_since is not None:
        git_kwargs["changed_since"] = changed_since
    if git_provenance is not None:
        git_kwargs["git_provenance"] = git_provenance
    elif getattr(search_cfg, "git_provenance", False) is True:
        git_kwargs["git_provenance"] = True
    if git_line_blame is not None:
        git_kwargs["git_line_blame"] = git_line_blame
    elif getattr(search_cfg, "git_line_blame", False) is True:
        git_kwargs["git_line_blame"] = True
    if git_rerank is not None:
        git_kwargs["git_rerank"] = git_rerank
    elif getattr(search_cfg, "git_rerank", False) is True:
        git_kwargs["git_rerank"] = True
    try:
        raw_results = svc_search(
            query,
            configs=configs,
            max_docs=search_cfg.max_docs,
            max_chunks=search_cfg.max_chunks,
            score_threshold=search_cfg.score_threshold,
            include_full_text=search_cfg.include_full_text,
            include_all_chunks=search_cfg.include_all_chunks,
            include_matched_chunks=search_cfg.include_matched_chunks,
            collections_path=collections_path,
            **git_kwargs,
        )
        return format_search_results_for_llm(raw_results, query)
    except IndexedError as e:
        return mcp_error_envelope(e)
    except Exception as e:  # noqa: BLE001 - MCP boundary must never leak a raw error
        logger.exception("Unexpected error while executing MCP search")
        return mcp_error_envelope(MCPError(f"Internal error: {e}"))


def _unresolvable_collection_envelope(
    collection: str, collections_path: str
) -> Dict[str, Any]:
    """``search_collection``'s unknown-vs-unusable answer (see ``collection_errors``)."""
    return unresolvable_collection_error(
        collection,
        collections_path,
        f"Collection '{collection}' not found or has no indexers",
    )


def register_tools(mcp: Any, get_search_config: Callable[[], Any]) -> None:
    """Register search tools on the FastMCP instance."""

    @mcp.tool
    def search(
        query: str,
        changed_since: Optional[str] = None,
        git_provenance: Optional[bool] = None,
        git_line_blame: Optional[bool] = None,
        git_rerank: Optional[bool] = None,
        ctx: Optional[Context] = None,
    ) -> Dict[str, Any]:
        """Search all available document collections for semantically similar content.

        Returns results in an LLM-optimized format with flat structure and direct text access.
        Results are ranked by relevance with the most relevant chunks first.

        Parameters:
            query (str): The search query text.
            changed_since (Optional[str]): Keep only files changed since this git ref,
                tag or commit, including uncommitted and untracked changes. A collection
                the filter cannot be applied to is named in ``collection_errors``.
            git_provenance (Optional[bool]): Add git_commit/git_author/git_committed_at
                to each result row (defaults to core.v1.search.git_provenance).
            git_line_blame (Optional[bool]): Add git_line_commit/git_line_author/
                git_line_committed_at to rows whose chunk records a line span
                (defaults to core.v1.search.git_line_blame).
            git_rerank (Optional[bool]): Re-rank by git recency, churn and author
                signals, with the blended score reported as score_kind git-rerank
                (defaults to core.v1.search.git_rerank).
            ctx (Optional[Context]): FastMCP Context (optional, for accessing lifespan state).

        Returns:
            dict: LLM-friendly search results with ranked results containing
                rank, relevance_score, collection, document_id, document_url,
                chunk_number, and text fields.
        """
        search_cfg = _resolve_config(ctx, "search_config", get_search_config)
        cli_ctx = resolve_cli_context(ctx)
        collections_path = str(cli_ctx.collections_path)

        return _run_search(
            query,
            None,
            search_cfg,
            collections_path,
            changed_since=changed_since,
            git_provenance=git_provenance,
            git_line_blame=git_line_blame,
            git_rerank=git_rerank,
        )

    @mcp.tool
    def search_collection(
        collection: str,
        query: str,
        changed_since: Optional[str] = None,
        git_provenance: Optional[bool] = None,
        git_line_blame: Optional[bool] = None,
        git_rerank: Optional[bool] = None,
        ctx: Optional[Context] = None,
    ) -> Dict[str, Any]:
        """Search within a specific document collection using semantic similarity.

        Returns results in the same LLM-optimized format as the general search tool.

        Args:
            collection: Name of the collection to search
            query: The search query text
            changed_since: Keep only files changed since this git ref, tag or commit
                (a collection the filter cannot be applied to is named in
                collection_errors)
            git_provenance: Add git_commit/git_author/git_committed_at to each result row
                (defaults to core.v1.search.git_provenance)
            git_line_blame: Add git_line_commit/git_line_author/git_line_committed_at
                to rows whose chunk records a line span
                (defaults to core.v1.search.git_line_blame)
            git_rerank: Re-rank by git recency, churn and author signals
                (defaults to core.v1.search.git_rerank)
            ctx: FastMCP Context (optional, for accessing lifespan state)

        Returns:
            dict: LLM-friendly search results with the same structure as search() tool
        """
        search_cfg = _resolve_config(ctx, "search_config", get_search_config)
        cli_ctx = resolve_cli_context(ctx)
        collections_path = str(cli_ctx.collections_path)

        try:
            statuses = svc_status([collection], collections_path=collections_path)
        except IndexedError as e:
            return mcp_error_envelope(e)
        except Exception as e:  # noqa: BLE001 - MCP boundary must never leak a raw error
            logger.exception(
                "Unexpected error resolving status for collection '{}'", collection
            )
            return mcp_error_envelope(MCPError(f"Internal error: {e}"))

        if not statuses or not statuses[0].indexers:
            return _unresolvable_collection_envelope(collection, collections_path)
        coll_status = statuses[0]
        default_indexer = coll_status.indexers[0]

        raw_source_type = coll_status.source_type if coll_status.source_type else None
        # Whitelist against the SourceConfig Literal; unknown on-disk types fall back
        # to "localFiles" so a corrupt manifest never raises ValidationError.
        source_type = (
            raw_source_type
            if raw_source_type in _ALLOWED_SOURCE_TYPES
            else "localFiles"
        )
        # source_type is runtime-validated against _ALLOWED_SOURCE_TYPES above
        # (deliberately derived from SourceConfig's own Literal via get_args()
        # rather than a hardcoded duplicate list, so this can't drift from the
        # model) — a static checker can't see through that indirection.
        source_config = SourceConfig(
            name=collection,
            type=source_type,
            base_url_or_path="",
            indexer=default_indexer,
        )

        return _run_search(
            query,
            [source_config],
            search_cfg,
            collections_path,
            changed_since=changed_since,
            git_provenance=git_provenance,
            git_line_blame=git_line_blame,
            git_rerank=git_rerank,
        )
