"""Unit tests for ``mcp.formatting.format_search_results_for_llm`` (core-v2/2d).

R11 (v2 side) + R4 parity: a v2 collection's ``scoreKind: "cosine"`` (higher
is better) must sort best-first, while a v1 collection (no ``scoreKind`` key
at all) keeps its existing ascending/lower-is-better sort byte-identical
(R6) — this is a per-collection, NOT a cross-engine, ordering fix; true
cross-engine value unification is a later unit.
"""

from __future__ import annotations

from indexed.mcp.formatting import format_search_results_for_llm


def _chunk(doc_id: str, score: float) -> dict:
    return {
        "id": doc_id,
        "url": f"u/{doc_id}",
        "matchedChunks": [
            {
                "chunkNumber": 0,
                "score": score,
                "content": {"indexedData": f"text for {doc_id}"},
            }
        ],
    }


def test_v1_collection_without_score_kind_sorts_ascending_lower_better() -> None:
    """No 'scoreKind' key at all (v1's real shape) — unchanged behavior."""
    raw = {
        "v1-coll": {
            "collectionName": "v1-coll",
            "results": [_chunk("worst", 3.0), _chunk("best", 0.1)],
        }
    }
    out = format_search_results_for_llm(raw, "q")
    ids = [r["document_id"] for r in out["results"]]
    assert ids == ["best", "worst"]


def test_v2_collection_with_cosine_score_kind_sorts_descending_higher_better() -> None:
    """v2's 'scoreKind: cosine' — higher score must rank first."""
    raw = {
        "v2-coll": {
            "collectionName": "v2-coll",
            "scoreKind": "cosine",
            "results": [_chunk("worst", 0.02), _chunk("best", 0.9)],
        }
    }
    out = format_search_results_for_llm(raw, "q")
    ids = [r["document_id"] for r in out["results"]]
    assert ids == ["best", "worst"]


def test_mixed_collections_each_sorted_by_their_own_score_kind() -> None:
    """Each collection's chunks rank correctly among themselves even when
    v1 (ascending) and v2 (descending) results are merged in one call — a
    true cross-engine VALUE comparison is out of scope here (later unit)."""
    raw = {
        "v1-coll": {
            "collectionName": "v1-coll",
            "results": [_chunk("v1-best", 0.1), _chunk("v1-worst", 3.0)],
        },
        "v2-coll": {
            "collectionName": "v2-coll",
            "scoreKind": "cosine",
            "results": [_chunk("v2-worst", 0.02), _chunk("v2-best", 0.9)],
        },
    }
    out = format_search_results_for_llm(raw, "q")
    by_collection = {
        "v1": [
            r["document_id"] for r in out["results"] if r["collection"] == "v1-coll"
        ],
        "v2": [
            r["document_id"] for r in out["results"] if r["collection"] == "v2-coll"
        ],
    }
    assert by_collection["v1"] == ["v1-best", "v1-worst"]
    assert by_collection["v2"] == ["v2-best", "v2-worst"]


def test_relevance_score_field_keeps_the_raw_unmodified_value() -> None:
    """The sort key is negated internally for cosine, but the PUBLIC
    'relevance_score' field must still carry the true, unmodified score."""
    raw = {
        "v2-coll": {
            "collectionName": "v2-coll",
            "scoreKind": "cosine",
            "results": [_chunk("d1", 0.75)],
        }
    }
    out = format_search_results_for_llm(raw, "q")
    assert out["results"][0]["relevance_score"] == 0.75
    assert "_sort_key" not in out["results"][0]
