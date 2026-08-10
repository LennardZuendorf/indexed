"""LLM-optimized formatting for MCP search results."""

from __future__ import annotations

from typing import Any


def format_search_results_for_llm(
    raw_results: dict[str, Any], query: str
) -> dict[str, Any]:
    """Transform raw search results into an LLM-optimized format.

    Flattens nested structures, extracts content directly, and provides
    clear context for each result with relevance ranking.
    """
    formatted: dict[str, Any] = {
        "query": query,
        "total_collections_searched": 0,
        "total_documents_found": 0,
        "total_chunks_found": 0,
        "results": [],
    }

    all_chunks: list[dict[str, Any]] = []
    # A failed collection must reach the agent as "index failed", not a
    # silent "0 matches" (foundation/6 E10) — collected here and always
    # included in the envelope below, even when empty.
    collection_errors: list[dict[str, Any]] = []

    for collection_name, collection_data in raw_results.items():
        if isinstance(collection_data, dict) and "error" in collection_data:
            collection_errors.append(
                {"collection": collection_name, "error": collection_data["error"]}
            )
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
                        }
                    )

    all_chunks.sort(key=lambda x: x["relevance_score"])

    for idx, chunk in enumerate(all_chunks, 1):
        chunk["rank"] = idx
        formatted["results"].append(chunk)

    formatted["total_chunks_found"] = len(all_chunks)
    formatted["collection_errors"] = collection_errors

    return formatted
