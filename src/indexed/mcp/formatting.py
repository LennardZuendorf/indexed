"""LLM-optimized formatting for MCP search results."""

from __future__ import annotations

from typing import Any, Dict, List

# Score kinds recorded per-collection (v2's ``scoreKind`` field, tech.md "V2
# manifest") for which a HIGHER score is a BETTER match. v1 carries no
# ``scoreKind`` key at all — ``dict.get`` defaults it out of this set, so a v1
# collection's sort key is UNCHANGED (R6: v1-only output byte-identical).
_HIGHER_IS_BETTER = frozenset({"cosine"})


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

    for collection_name, collection_data in raw_results.items():
        if isinstance(collection_data, dict) and "error" in collection_data:
            collection_errors.append(
                {"collection": collection_name, "error": collection_data["error"]}
            )
            continue

        formatted["total_collections_searched"] += 1

        if not isinstance(collection_data, dict) or "results" not in collection_data:
            continue

        # v1 carries no "scoreKind" (squared-L2, lower-better, the sort default
        # below); v2 records "cosine" (higher-better) per collection (R11 v2
        # side; full cross-engine value unification is a later unit — this only
        # orders each collection's OWN chunks correctly).
        higher_is_better = collection_data.get("scoreKind") in _HIGHER_IS_BETTER

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
                            # Sort-only, not part of the public envelope shape —
                            # popped off again right below.
                            "_sort_key": -score if higher_is_better else score,
                        }
                    )

    all_chunks.sort(key=lambda x: x["_sort_key"])
    for chunk in all_chunks:
        del chunk["_sort_key"]

    for idx, chunk in enumerate(all_chunks, 1):
        chunk["rank"] = idx
        formatted["results"].append(chunk)

    formatted["total_chunks_found"] = len(all_chunks)
    formatted["collection_errors"] = collection_errors

    return formatted
