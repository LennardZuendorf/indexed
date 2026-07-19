"""LLM-optimized formatting for MCP search results."""

from __future__ import annotations

from typing import Any, Dict, List

# Score kinds recorded per-collection (v2's ``scoreKind`` field, tech.md "V2
# manifest") for which a HIGHER score is a BETTER match. v1 carries no
# ``scoreKind`` key at all — ``dict.get`` defaults it out of this set, so a v1
# collection's sort key is UNCHANGED (R6: v1-only output byte-identical).
_HIGHER_IS_BETTER = frozenset({"cosine"})


def _unified_relevance(raw_score: float, higher_is_better: bool) -> float:
    """Map a raw per-engine score onto one comparable measure — cosine (R11).

    v2 already reports cosine similarity (``higher_is_better``) so its raw score
    IS the relevance. v1 reports a squared-L2 distance ``d²`` over
    unit-normalized vectors, so ``sim = 1 - d²/2`` recovers the cosine exactly.
    Higher is better in both cases, so a merged view sorts on it directly.
    """
    if higher_is_better:
        return raw_score
    return 1.0 - raw_score / 2.0


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
        # "cosine" (higher-better) per collection.
        higher_is_better = collection_data.get("scoreKind") in _HIGHER_IS_BETTER
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
                            # returned. Carries the owning collection's score
                            # direction to the cross-engine sort below.
                            "_higher_is_better": higher_is_better,
                        }
                    )

    _rank_chunks(all_chunks, unified=any_higher_is_better)
    for chunk in all_chunks:
        del chunk["_higher_is_better"]

    for idx, chunk in enumerate(all_chunks, 1):
        chunk["rank"] = idx
        formatted["results"].append(chunk)

    formatted["total_chunks_found"] = len(all_chunks)
    formatted["collection_errors"] = collection_errors

    return formatted


def _rank_chunks(all_chunks: List[Dict[str, Any]], *, unified: bool) -> None:
    """Order ``all_chunks`` best-first, in place (R11 cross-engine / R6 v1-only).

    ``unified=True`` (a v2 collection is present, mixed or v2-only): every chunk
    gets a ``relevance`` on ONE comparable measure (cosine, via
    ``_unified_relevance``) plus a ``score_kind`` label; the raw
    ``relevance_score`` is left untouched (each engine's raw score preserved).
    Sort is by ``relevance`` DESCENDING.

    ``unified=False`` (v1-only, no ``scoreKind`` anywhere): the EXACT pre-feature
    path — ascending raw score, and NO ``relevance``/``score_kind`` field added —
    so a v1-only search's output is byte-identical to before this feature (R6).
    """
    if not unified:
        all_chunks.sort(key=lambda c: c["relevance_score"])
        return

    for chunk in all_chunks:
        higher_is_better = chunk["_higher_is_better"]
        chunk["relevance"] = _unified_relevance(
            chunk["relevance_score"], higher_is_better
        )
        chunk["score_kind"] = "cosine" if higher_is_better else "l2_squared"
    all_chunks.sort(key=lambda c: c["relevance"], reverse=True)
