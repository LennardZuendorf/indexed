"""LLM-optimized formatting for MCP search results."""

from __future__ import annotations

from typing import Any, Dict, List

from indexed.utils.relevance import HIGHER_IS_BETTER, unified_relevance


def format_search_results_for_llm(
    raw_results: Dict[str, Any], query: str
) -> Dict[str, Any]:
    """Transform raw search results into an LLM-optimized format.

    Flattens nested structures, extracts content directly, and provides
    clear context for each result with relevance ranking.
    """
    formatted: Dict[str, Any] = {
        "query": query,
        "total_collections_searched": 0,
        "total_documents_found": 0,
        "total_chunks_found": 0,
        "results": [],
    }

    all_chunks: List[Dict[str, Any]] = []
    # A failed collection must reach the agent as "index failed", not a
    # silent "0 matches" (foundation/6 E10) — collected here and always
    # included in the envelope below, even when empty.
    collection_errors: List[Dict[str, Any]] = []
    # Whether ANY v2 collection (scoreKind cosine) is in the merged set. Only
    # then does the cross-engine cosine unification apply (R11); a v1-only view
    # keeps the EXACT pre-feature path so its output is byte-identical (R6).
    any_higher_is_better = False

    for collection_name, collection_data in raw_results.items():
        if isinstance(collection_data, dict) and "error" in collection_data:
            collection_errors.append(
                {"collection": collection_name, "error": collection_data["error"]}
            )
            continue

        formatted["total_collections_searched"] += 1

        if not isinstance(collection_data, dict) or "results" not in collection_data:
            continue

        # v1 carries no "scoreKind" (squared-L2, lower-better); v2 records
        # "cosine" or "rerank" (both higher-better) per collection.
        raw_score_kind = collection_data.get("scoreKind")
        higher_is_better = raw_score_kind in HIGHER_IS_BETTER
        if higher_is_better:
            any_higher_is_better = True

        documents = collection_data.get("results", [])
        formatted["total_documents_found"] += len(documents)

        for doc in documents:
            doc_id = doc.get("id", "unknown")
            doc_url = doc.get("url", "")
            matched_chunks = doc.get("matchedChunks", [])

            for chunk_data in matched_chunks:
                chunk_number = chunk_data.get("chunkNumber", 0)
                score = chunk_data.get("score", 999.0)

                content_text = ""
                if "content" in chunk_data:
                    content = chunk_data["content"]
                    if isinstance(content, dict) and "indexedData" in content:
                        content_text = content["indexedData"]
                    elif isinstance(content, str):
                        content_text = content

                if content_text:
                    all_chunks.append(
                        {
                            "rank": 0,
                            "relevance_score": score,
                            "collection": collection_name,
                            "document_id": doc_id,
                            "document_url": doc_url,
                            "chunk_number": chunk_number,
                            "text": content_text,
                            # Sort helper only, popped before the envelope is
                            # returned. The real score_kind ("cosine"/"rerank")
                            # when known, else None (v1 / unknown kind).
                            "_score_kind": raw_score_kind if higher_is_better else None,
                        }
                    )

    _rank_chunks(all_chunks, unified=any_higher_is_better)
    for chunk in all_chunks:
        del chunk["_score_kind"]

    for idx, chunk in enumerate(all_chunks, 1):
        chunk["rank"] = idx
        formatted["results"].append(chunk)

    formatted["total_chunks_found"] = len(all_chunks)
    formatted["collection_errors"] = collection_errors

    return formatted


def _rank_chunks(all_chunks: List[Dict[str, Any]], *, unified: bool) -> None:
    """Order ``all_chunks`` best-first, in place (R11 cross-engine / R6 v1-only).

    ``unified=True`` (a v2 collection is present, mixed or v2-only): every
    chunk gets a ``relevance`` on one comparable measure via
    ``unified_relevance`` (bounded (0,1) even for an unbounded rerank logit,
    issue #186) plus a ``score_kind`` label carrying the REAL kind
    ("cosine"/"rerank"/"l2_squared") — not a boolean-derived guess. The raw
    ``relevance_score`` is left untouched.

    ``unified=False`` (v1-only, no ``scoreKind`` anywhere): the EXACT
    pre-feature path — ascending raw score, no ``relevance``/``score_kind``
    field added — so a v1-only search's output is byte-identical (R6).
    """
    if not unified:
        all_chunks.sort(key=lambda c: c["relevance_score"])
        return

    for chunk in all_chunks:
        score_kind = chunk["_score_kind"] or "l2_squared"
        chunk["relevance"] = unified_relevance(chunk["relevance_score"], score_kind)
        chunk["score_kind"] = score_kind
    all_chunks.sort(key=lambda c: c["relevance"], reverse=True)
