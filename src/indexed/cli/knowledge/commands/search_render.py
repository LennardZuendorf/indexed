"""Rendering helpers for the search command.

Extracted from ``search.py`` (thin command, fat service): the command parses
args, runs the search, and delegates all result formatting here. These helpers
own the card-based display of search results, including the Foundation markup
escaping (foundation/6c bug E2) and per-collection failure surfacing
(foundation/6 E10, CLI twin of the MCP formatting bug).
"""

from typing import Any, Dict, List, TypedDict

# Raw Panel needed — free-text excerpt content doesn't fit card components
from rich.panel import Panel
from rich.markup import escape

from ...utils.console import console
from ...utils.components.theme import get_heading_style, get_accent_style
from ...utils.components import (
    create_summary,
    create_detail_card,
    get_card_border_style,
    get_card_padding,
    get_secondary_style,
    get_dim_style,
    print_error,
    print_warning,
)
from ...utils.components.theme import get_detail_card_width

# Score kinds (v2's per-collection ``scoreKind`` field) for which a HIGHER
# score is a BETTER match. v1 results carry no ``scoreKind`` key at all, so
# ``dict.get`` defaults a v1 collection out of this set — its sort key stays
# exactly the raw ascending score, byte-identical to before (R6). "rerank" is
# a cross-encoder relevance (also higher-is-better) reported when
# ``[core.v2.rerank] enabled=true`` replaces the cosine score (PR #158 review).
_HIGHER_IS_BETTER = frozenset({"cosine", "rerank"})


def _unified_relevance(raw_score: float, higher_is_better: bool) -> float:
    """Map a raw per-engine score onto one comparable measure — cosine (R11).

    v2 already reports cosine similarity (``higher_is_better``) so its raw score
    IS the relevance; v1 reports a squared-L2 distance ``d²`` over
    unit-normalized vectors, so ``sim = 1 - d²/2`` recovers the cosine exactly.
    Pure arithmetic (mirrors ``mcp/formatting`` so CLI and MCP agree) — the
    app-layer never imports ``core.v2`` for this.
    """
    if higher_is_better:
        return raw_score
    return 1.0 - raw_score / 2.0


class ChunkInfo(TypedDict):
    collection: str
    doc_id: str
    path: str
    chunk: Dict[str, Any]
    chunk_index: int


def _is_content_free(chunk_info: ChunkInfo) -> bool:
    """True when a chunk's text is empty, or is just its document's name (a
    title/filename chunk) — useless as the highlighted excerpt (UX finding
    M1). Every document carries a ``chunk_number 0`` whose text is only the
    filename, which for NL queries often out-scores real content.

    Content that's missing entirely (no ``content`` key, ``content`` isn't a
    dict, or no ``indexedData`` key at all) is treated as NOT content-free —
    there's nothing to compare, so top-result selection stays exactly
    ``all_chunks[0]``, unchanged from before this fix. But content that IS
    present and is an empty string, or equals the doc id / basename, IS
    content-free.
    """
    obj = chunk_info["chunk"].get("content")
    if not isinstance(obj, dict):
        return False
    raw = obj.get("indexedData")
    if raw is None:
        return False
    content = str(raw).strip()
    doc = str(chunk_info["doc_id"]).strip()
    base = doc.rsplit("/", 1)[-1]
    return content in ("", doc, base)


def _print_collection_errors(failed: List[tuple[str, Any]]) -> None:
    """Surface a per-collection search failure instead of silently skipping it.

    Mirrors the MCP-side fix (``mcp/formatting.py``): a failed collection must
    reach the user as "index failed", not vanish via a bare ``continue``
    (foundation/6 E10, CLI twin of the same bug).
    """
    for collection_name, error in failed:
        # collection_name/error are content-derived — escape before entering
        # markup (foundation/6c bug E2).
        print_error(
            f"Collection '{escape(str(collection_name))}' failed: {escape(str(error))}"
        )


def format_search_results(
    query: str,
    results: Dict[str, Any],
    limit: int = 5,
    show_content: bool = True,
) -> None:
    """Display search results with single top result and compact list of others.

    Shows the single most relevant chunk with full content excerpt in a card,
    then lists the next 4 matches in a compact format showing collection/doc/chunk.

    Args:
        query: The search query
        results: Dictionary with collection names as keys and result data as values
        limit: Maximum number of total results to show (unused, kept for compatibility)
        show_content: Whether to show content previews
    """
    console.print()

    if not show_content:
        # If content hidden, use compact format
        _show_all_results_compact(results, limit)
        return

    # Collect all chunks across all collections with their metadata
    all_chunks: List[ChunkInfo] = []
    total_docs = 0
    failed_collections: List[tuple[str, Any]] = []
    # Per-collection score direction (v2's "scoreKind"; v1 has none, so it
    # defaults to the ascending/lower-is-better convention — R6 byte-stable).
    higher_is_better_by_collection: Dict[str, bool] = {}
    # Raw scoreKind string per collection ("cosine"/"rerank"), threaded through
    # so rendered scores can carry a scale label (R6) — v1 collections have no
    # scoreKind key and stay absent from this dict (unlabeled, byte-stable).
    score_kind_by_collection: Dict[str, str] = {}

    for collection_name, collection_results in results.items():
        if "error" in collection_results:
            failed_collections.append((collection_name, collection_results["error"]))
            continue

        raw_score_kind = collection_results.get("scoreKind")
        higher_is_better_by_collection[collection_name] = (
            raw_score_kind in _HIGHER_IS_BETTER
        )
        if isinstance(raw_score_kind, str):
            score_kind_by_collection[collection_name] = raw_score_kind

        documents = collection_results.get("results", [])
        total_docs += len(documents)

        for doc in documents:
            doc_id = doc.get("id", "Unknown")
            path = doc.get("path") or doc.get("url", "")
            matched_chunks = doc.get("matchedChunks", []) or doc.get(
                "matched_chunks", []
            )

            for i, chunk in enumerate(matched_chunks):
                all_chunks.append(
                    ChunkInfo(
                        collection=collection_name,
                        doc_id=doc_id,
                        path=path,
                        chunk=chunk,
                        chunk_index=i + 1,  # 1-indexed for display
                    )
                )

    if failed_collections:
        _print_collection_errors(failed_collections)
        console.print()

    if not all_chunks:
        if not failed_collections:
            print_warning(
                f'No results found for "{query}". '
                f"Try broadening your search terms or checking collection contents."
            )
        console.print()
        return

    # Sort chunks best-first. When a v2 collection is present (mixed or
    # v2-only) rank ALL chunks on one comparable measure — cosine relevance,
    # v1's squared-L2 mapped ``sim = 1 - d²/2`` (R11) — descending. When the
    # view is v1-only (no scoreKind anywhere) keep the EXACT pre-feature sort
    # (ascending raw distance), so v1-only display order is byte-identical (R6).
    # The displayed score is always the untouched raw score (preserved).
    any_v2 = any(higher_is_better_by_collection.values())
    if any_v2:

        def _sort_key(x: ChunkInfo) -> float:
            hib = higher_is_better_by_collection.get(x["collection"], False)
            return -_unified_relevance(x["chunk"].get("score", 999), hib)
    else:

        def _sort_key(x: ChunkInfo) -> float:
            return x["chunk"].get("score", 999)

    all_chunks.sort(key=_sort_key, reverse=False)

    # Show top result with split meta/excerpt cards
    console.print(
        f"[{get_heading_style()}]Best Matched Search Result:[/{get_heading_style()}]"
    )
    console.print()
    # M1: chunk_number 0 is always just the document's filename — for NL
    # queries it often out-scores real content, so surfacing it as the
    # highlighted excerpt is a useless first impression. Pick the
    # highest-ranked chunk with real content instead; fall back to
    # all_chunks[0] if every candidate is content-free. Other Matches (below)
    # draws from this SAME filtered pool (R5) — otherwise a content-free
    # chunk skipped here survives unfiltered into Other Matches, ranked above
    # wherever the promoted top actually landed.
    non_free = [c for c in all_chunks if not _is_content_free(c)]
    top = non_free[0] if non_free else all_chunks[0]
    _show_top_result_split_cards(
        top,
        show_relevance=any_v2,
        higher_is_better_by_collection=higher_is_better_by_collection,
        score_kind_by_collection=score_kind_by_collection,
    )

    # Show next 4 results in compact format, excluding whichever chunk got
    # promoted to the highlighted top — by identity, so only the exact
    # promoted object is skipped, not other chunks with an equal score
    # (review finding: a content-free #1 promotes some all_chunks[k], k>=1,
    # which the old positional all_chunks[1:5] slice could still include,
    # duplicating it in both the highlight and the list). Drawn from
    # `non_free` (R5) so a content-free chunk never leaks into this list
    # either; falls back to `all_chunks` only when every chunk is
    # content-free (matching the fallback used for `top` above).
    others = [c for c in (non_free or all_chunks) if c is not top][:4]
    if others:
        console.print()
        console.print(
            f"[{get_heading_style()}]Other Search Query Matches[/{get_heading_style()}]"
        )
        console.print()

        for chunk_info in others:
            _show_compact_match(
                chunk_info,
                show_relevance=any_v2,
                higher_is_better_by_collection=higher_is_better_by_collection,
                score_kind_by_collection=score_kind_by_collection,
            )

    # Summary
    console.print()
    summary = create_summary(
        "Search Result",
        f"Found {len(all_chunks)} matching chunks across {total_docs} documents",
    )
    console.print(summary)
    console.print()


def _show_top_result_split_cards(
    chunk_info: ChunkInfo,
    show_relevance: bool = False,
    higher_is_better_by_collection: Dict[str, bool] | None = None,
    score_kind_by_collection: Dict[str, str] | None = None,
) -> None:
    """Show the top result chunk in two cards: Meta and Excerpt."""

    collection = chunk_info["collection"]
    doc_id = chunk_info["doc_id"]
    chunk = chunk_info["chunk"]
    chunk_index = chunk_info["chunk_index"]

    # --- METADATA CARD ---
    meta_rows = []
    meta_rows.append(("Collection", collection))
    meta_rows.append(("Document", doc_id))

    score = chunk.get("score")
    score_str = (
        f"{score:.4f}"
        if isinstance(score, float)
        else (str(score) if score is not None else "N/A")
    )
    # R6: label the score with its scale (cosine/rerank) when known, so a
    # rerank score's unbounded range isn't mistaken for cosine's [0, 1].
    score_kind = (score_kind_by_collection or {}).get(collection)
    if score_kind:
        score_str = f"{score_str} ({score_kind})"
    meta_rows.append(("Score", score_str))

    # Mixed v1+v2 view: surface one comparable relevance measure right after
    # the raw score (M2/R11 CLI display) — v1-only view stays byte-identical
    # (R6), since ``show_relevance`` is only True when a v2 collection is
    # present in the result set.
    if show_relevance and isinstance(score, (int, float)):
        hib = (higher_is_better_by_collection or {}).get(collection, False)
        rel = _unified_relevance(float(score), hib)
        meta_rows.append(("Relevance", f"{rel:.4f}"))

    meta_rows.append(("Chunk", str(chunk_index)))

    # Only include match id if available
    chunk_id = chunk.get("id")
    if chunk_id:
        meta_rows.append(("Match ID", chunk_id))

    meta_card = create_detail_card(title="Top Result Meta", rows=meta_rows)
    console.print(meta_card)

    # --- EXCERPT CARD ---
    # Get chunk excerpt
    chunk_content_obj = chunk.get("content", {})
    if isinstance(chunk_content_obj, dict):
        chunk_content = chunk_content_obj.get("indexedData", "")
    else:
        chunk_content = str(chunk_content_obj)
    excerpt = chunk_content.strip() if chunk_content else ""
    max_length = 1500
    display_excerpt = (
        excerpt if len(excerpt) <= max_length else excerpt[:max_length] + "..."
    )

    # Use a subtle dim/muted style for the excerpt card with same width as meta card.
    # `display_excerpt` is indexed document content — untrusted — so it must be
    # escaped before entering this markup string; the surrounding dim-style
    # tags are ours and stay as-is (foundation/6c bug E2).
    excerpt_panel = Panel(
        f"[{get_dim_style()}]{escape(display_excerpt)}[/{get_dim_style()}]"
        if excerpt
        else f"[{get_dim_style()}][No excerpt available][/{get_dim_style()}]",
        title="Top Result Excerpt",
        border_style=get_card_border_style(),
        padding=get_card_padding(),
        style=get_secondary_style(),
        width=get_detail_card_width(),  # Match the meta card width
    )
    console.print(excerpt_panel)


def _show_compact_match(
    chunk_info: ChunkInfo,
    show_relevance: bool = False,
    higher_is_better_by_collection: Dict[str, bool] | None = None,
    score_kind_by_collection: Dict[str, str] | None = None,
) -> None:
    """Show a compact single-line match."""
    collection = chunk_info["collection"]
    doc_id = chunk_info["doc_id"]
    chunk = chunk_info["chunk"]
    chunk_index = chunk_info["chunk_index"]
    score = chunk.get("score", "N/A")
    if isinstance(score, float):
        chunk_score = f"{score:.4f}"
    else:
        chunk_score = str(score)

    # R6: same scale label as the top-result meta card, kept before the
    # relevance suffix so both stay readable on one compact line.
    score_kind = (score_kind_by_collection or {}).get(collection)
    if score_kind:
        chunk_score = f"{chunk_score} ({score_kind})"

    # Mixed v1+v2 view: append the same comparable relevance measure shown on
    # the top card (M2/R11) — v1-only view stays byte-identical (R6).
    rel_suffix = ""
    if show_relevance and isinstance(score, (int, float)):
        hib = (higher_is_better_by_collection or {}).get(collection, False)
        rel = _unified_relevance(float(score), hib)
        rel_suffix = f" / rel {rel:.4f}"

    # Format: collection / document / part / match_id
    # collection/doc_id/chunk_score are user/content-derived (collection name,
    # document path or URL, indexed data) — escape before entering this markup
    # string; the surrounding style tags are ours (foundation/6c bug E2).
    console.print(
        f"  • [{get_accent_style()}]{escape(collection)}[/{get_accent_style()}] / "
        f"{escape(str(doc_id))} / "
        f"[{get_dim_style()}]Chunk {chunk_index}[/{get_dim_style()}] / "
        f"[{get_dim_style()}]{escape(chunk_score)}[/{get_dim_style()}]{rel_suffix}"
    )


def _show_all_results_compact(results: Dict[str, Any], limit: int) -> None:
    """Show all results in compact format when content is hidden."""
    total_results = 0
    failed_collections: List[tuple[str, Any]] = []

    for collection_name, collection_results in results.items():
        if "error" in collection_results:
            failed_collections.append((collection_name, collection_results["error"]))
            continue

        documents = collection_results.get("results", [])
        if not documents:
            continue

        total_results += len(documents)

        # Collection header — collection_name/doc_id are content-derived, so
        # escape them before entering markup (foundation/6c bug E2).
        console.print(
            f"[{get_accent_style()}]{escape(collection_name)}[/{get_accent_style()}] [{get_dim_style()}]({len(documents)} results)[/{get_dim_style()}]"
        )

        # List results
        for i, doc in enumerate(documents[:limit], 1):
            doc_id = doc.get("id", "Unknown")
            console.print(f"  {i}. {escape(str(doc_id))}")

        console.print()

    if failed_collections:
        _print_collection_errors(failed_collections)
        console.print()

    # Summary
    console.print()
    if total_results > 0:
        console.print(create_summary("Search Result", f"{total_results} results"))
    elif not failed_collections:
        console.print(f"[{get_dim_style()}]No results found[/{get_dim_style()}]")

    console.print()


def format_search_results_compact(
    query: str,
    results: Dict[str, Any],
    limit: int = 10,
) -> None:
    """Display search results in compact list format.

    Args:
        query: The search query
        results: Dictionary with collection names as keys and result data as values
        limit: Maximum number of results to show per collection
    """

    total_results = 0
    failed_collections: List[tuple[str, Any]] = []

    for collection_name, collection_results in results.items():
        if "error" in collection_results:
            failed_collections.append((collection_name, collection_results["error"]))
            continue

        documents = collection_results.get("results", [])
        if not documents:
            continue

        total_results += len(documents)

        # Collection header — collection_name/doc_id are content-derived, so
        # escape them before entering markup (foundation/6c bug E2).
        console.print(
            f"[{get_accent_style()}]{escape(collection_name)}[/{get_accent_style()}] [{get_dim_style()}]({len(documents)} results)[/{get_dim_style()}]"
        )

        # List results
        for i, doc in enumerate(documents[:limit], 1):
            doc_id = doc.get("id", "Unknown")
            score = doc.get("score")

            if score is not None:
                score_str = (
                    f" [{score:.4f}]" if isinstance(score, float) else f" [{score}]"
                )
                console.print(
                    f"  {i}. {escape(str(doc_id))}[{get_dim_style()}]{score_str}[/{get_dim_style()}]"
                )
            else:
                console.print(f"  {i}. {escape(str(doc_id))}")

        console.print()

    if failed_collections:
        _print_collection_errors(failed_collections)
        console.print()

    # Summary
    console.print()
    if total_results > 0:
        console.print(create_summary("Search Result", f"{total_results} results"))
    elif not failed_collections:
        console.print(f"[{get_dim_style()}]No results found[/{get_dim_style()}]")

    console.print()
