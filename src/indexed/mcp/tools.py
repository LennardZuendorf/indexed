"""MCP tool implementations for search operations."""

import asyncio
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
from indexed.cli.search_sources import declare_sources, scope_of
from .collection_errors import unresolvable_collection_error
from .config import resolve_config as _resolve_config
from .formatting import build_search_payload
from .scope import require_in_scope, resolve_request_scope

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
    sources: Optional[List[Dict[str, Any]]] = None,
    changed_since: Optional[str] = None,
    git_provenance: Optional[bool] = None,
    git_line_blame: Optional[bool] = None,
    git_rerank: Optional[bool] = None,
    include_freshness: Optional[bool] = None,
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
    if include_freshness:
        # Opt-in: the envelope then carries one freshness verdict per
        # collection, worded exactly as `index inspect` words it.
        git_kwargs["include_freshness"] = True
    try:
        raw_results = svc_search(
            query,
            configs=configs,
            max_docs=search_cfg.max_docs,
            max_chunks=search_cfg.max_chunks,
            score_threshold=search_cfg.score_threshold,
            include_full_text=search_cfg.include_full_text,
            include_all_chunks=search_cfg.include_all_chunks,
            include_matched_chunks=True,
            collections_path=collections_path,
            **git_kwargs,
        )
        return build_search_payload(raw_results, query, sources=sources)
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


def _source_config(name: str, status: Any) -> SourceConfig:
    """Route one collection by its own manifest, never by a configured default."""
    raw_source_type = status.source_type if status.source_type else None
    # Whitelist against the SourceConfig Literal; unknown on-disk types fall back
    # to "localFiles" so a corrupt manifest never raises ValidationError.
    source_type = (
        raw_source_type if raw_source_type in _ALLOWED_SOURCE_TYPES else "localFiles"
    )
    return SourceConfig(
        name=name,
        type=source_type,
        base_url_or_path="",
        indexer=status.indexers[0],
    )


def register_tools(mcp: Any, get_search_config: Callable[[], Any]) -> None:
    """Register search tools on the FastMCP instance."""

    @mcp.tool
    async def search(
        query: str,
        changed_since: Optional[str] = None,
        git_provenance: Optional[bool] = None,
        git_line_blame: Optional[bool] = None,
        git_rerank: Optional[bool] = None,
        include_freshness: Optional[bool] = None,
        ctx: Optional[Context] = None,
    ) -> Dict[str, Any]:
        """Search the collections this client's repository selects.

        Scope is per request: the server reads the client's MCP roots, finds the
        committed `indexed.toml` at the repository root and searches exactly its
        selection from the global store. With no roots, no definition, or two
        conflicting definitions the call returns the documented error envelope
        (`NoRequestScopeError` / `AmbiguousRequestScopeError`) and searches
        nothing — it never falls back to every collection.

        Returns the documented machine payload (schema ``indexed.search/1``):
        matched documents, each stating its collection, source type, id, url
        and score semantics once, with `hits` carrying relevance, raw score, a
        locator and the chunk text. `locator.kind` is `line_span` (1-based
        inclusive, code), `page` (PDF/DOCX), `headings` (prose) or `document`
        (position unknown). See docs/spec/tech/app/app-search-result-contract.md.

        Parameters:
            query (str): The search query text.
            changed_since (Optional[str]): Keep only files changed since this git ref,
                tag or commit, including uncommitted and untracked changes. A collection
                the filter cannot be applied to is named in ``collection_errors``.
            git_provenance (Optional[bool]): Add the document-level ``git`` block
                (commit/short/author/committedAt/subject), omitted for a file
                changed since it was indexed
                (defaults to core.v1.search.git_provenance).
            git_line_blame (Optional[bool]): Add per-hit line blame when available.
            git_rerank (Optional[bool]): Re-rank by git recency, churn and author
                signals, with the blended score reported as score_kind git-rerank
                (defaults to core.v1.search.git_rerank).
            include_freshness (Optional[bool]): Add a per-collection ``freshness``
                verdict (fresh/stale/unknown) to the envelope — how far behind the
                source working tree each index is.
            ctx (Optional[Context]): FastMCP Context — carries this client's MCP
                roots, which decide the request's scope.

        Returns:
            dict: ``{schema, query, counts, collections, collection_errors,
                documents}`` — documents ranked by their best hit.
        """
        search_cfg = _resolve_config(ctx, "search_config", get_search_config)
        try:
            scope = await resolve_request_scope(ctx)
        except IndexedError as e:
            return mcp_error_envelope(e)
        collections_path = str(scope.collections_path)

        # The request's definition is the intended scope (#340/#345): declare it
        # first, answer from every selected collection the store can serve, and
        # let the payload name the ones it cannot. MCP used to pass
        # ``configs=None`` and search the whole store, so two surfaces of one
        # project answered different questions.
        try:
            # Off the event loop: status scans manifests and search is CPU/IO
            # bound (FAISS + embeddings). One long-lived server serves many
            # clients, so a blocking call here would stall every other request.
            statuses = await asyncio.to_thread(
                svc_status,
                list(scope.selection.scope),
                collections_path=collections_path,
            )
        except IndexedError as e:
            return mcp_error_envelope(e)
        except Exception as e:  # noqa: BLE001 - MCP boundary never leaks a raw error
            logger.exception("Unexpected error resolving the request's scope")
            return mcp_error_envelope(MCPError(f"Internal error: {e}"))

        scope_names, unresolved = scope_of(scope.selection, statuses)
        declarations = declare_sources(
            names=scope_names, statuses=statuses, unresolved=unresolved
        )
        by_name = {status.name: status for status in statuses}
        configs: List[SourceConfig] = []
        for declaration in declarations:
            if "status" in declaration:
                continue
            status = by_name.get(str(declaration["collection"]))
            if status is None or not status.indexers:
                continue
            configs.append(_source_config(str(declaration["collection"]), status))
        if not configs:
            # Every selected source is gone or unusable: answering from the
            # whole store would silently widen the scope. The payload says so.
            return build_search_payload({}, query, sources=declarations)

        return await asyncio.to_thread(
            _run_search,
            query,
            configs,
            search_cfg,
            collections_path,
            sources=declarations,
            changed_since=changed_since,
            git_provenance=git_provenance,
            git_line_blame=git_line_blame,
            git_rerank=git_rerank,
            include_freshness=include_freshness,
        )

    @mcp.tool
    async def search_collection(
        collection: str,
        query: str,
        changed_since: Optional[str] = None,
        git_provenance: Optional[bool] = None,
        git_line_blame: Optional[bool] = None,
        git_rerank: Optional[bool] = None,
        include_freshness: Optional[bool] = None,
        ctx: Optional[Context] = None,
    ) -> Dict[str, Any]:
        """Search within a specific document collection using semantic similarity.

        Returns the same documented payload as the general search tool
        (schema ``indexed.search/1``), restricted to one collection.

        The collection must be in this client's request scope (the selection of
        the `indexed.toml` at the repository root): a name outside it returns a
        `CollectionOutsideScopeError` envelope, so a client cannot reach another
        project's collections by naming one.

        Args:
            collection: Name of the collection to search
            query: The search query text
            changed_since: Keep only files changed since this git ref, tag or commit
                (a collection the filter cannot be applied to is named in
                collection_errors)
            git_provenance: Add the document-level ``git`` block
                (commit/short/author/committedAt/subject), omitted for a file
                changed since it was indexed
                (defaults to core.v1.search.git_provenance)
            git_line_blame: Add git_line_commit/git_line_author/git_line_committed_at
                to rows whose chunk records a line span
                (defaults to core.v1.search.git_line_blame)
            git_rerank: Re-rank by git recency, churn and author signals
                (defaults to core.v1.search.git_rerank)
            include_freshness: Add a per-collection freshness verdict (fresh/stale/
                unknown) to the envelope, in the same words `index inspect` uses
            ctx: FastMCP Context — carries this client's MCP roots (request scope)

        Returns:
            dict: LLM-friendly search results with the same structure as search() tool
        """
        search_cfg = _resolve_config(ctx, "search_config", get_search_config)
        try:
            scope = await resolve_request_scope(ctx)
            require_in_scope(scope, collection)
        except IndexedError as e:
            return mcp_error_envelope(e)
        collections_path = str(scope.collections_path)

        try:
            statuses = await asyncio.to_thread(
                svc_status, [collection], collections_path=collections_path
            )
        except IndexedError as e:
            return mcp_error_envelope(e)
        except Exception as e:  # noqa: BLE001 - MCP boundary must never leak a raw error
            logger.exception(
                "Unexpected error resolving status for collection '{}'", collection
            )
            return mcp_error_envelope(MCPError(f"Internal error: {e}"))

        if not statuses or not statuses[0].indexers:
            return _unresolvable_collection_envelope(collection, collections_path)
        source_config = _source_config(collection, statuses[0])

        return await asyncio.to_thread(
            _run_search,
            query,
            [source_config],
            search_cfg,
            collections_path,
            sources=declare_sources(names=[collection], statuses=statuses),
            changed_since=changed_since,
            git_provenance=git_provenance,
            git_line_blame=git_line_blame,
            git_rerank=git_rerank,
            include_freshness=include_freshness,
        )
