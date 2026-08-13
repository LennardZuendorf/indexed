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


# --- R11: cross-engine unified relevance -------------------------------------

# Pre-feature v1-only result chunk shape — the EXACT key set a v1-only search
# must still emit (no ``relevance``/``score_kind`` added). R6 byte-stability.
_V1_CHUNK_KEYS = {
    "rank",
    "relevance_score",
    "collection",
    "document_id",
    "document_url",
    "chunk_number",
    "text",
}


def test_mixed_v1_v2_ranks_on_one_comparable_relevance() -> None:
    """R11: with BOTH engines present, all chunks rank on one comparable
    measure — cosine, v1's squared-L2 mapped ``sim = 1 - d²/2`` — so a better
    v2 hit outranks a worse v1 hit and vice-versa (not 'v2 always first')."""
    raw = {
        # v1: squared-L2 distances (lower better). rel = 1 - d²/2.
        "v1-coll": {
            "collectionName": "v1-coll",
            "results": [_chunk("v1-strong", 0.1), _chunk("v1-weak", 1.6)],
        },
        # v2: cosine (higher better). rel = score.
        "v2-coll": {
            "collectionName": "v2-coll",
            "scoreKind": "cosine",
            "results": [_chunk("v2-strong", 0.9), _chunk("v2-weak", 0.4)],
        },
    }
    out = format_search_results_for_llm(raw, "q")
    ids = [r["document_id"] for r in out["results"]]
    # relevances: v1-strong 0.95 > v2-strong 0.90 > v2-weak 0.40 > v1-weak 0.20
    assert ids == ["v1-strong", "v2-strong", "v2-weak", "v1-weak"]

    by_id = {r["document_id"]: r for r in out["results"]}
    # Each engine's RAW score field is preserved untouched.
    assert by_id["v1-strong"]["relevance_score"] == 0.1
    assert by_id["v2-strong"]["relevance_score"] == 0.9
    # Unified relevance is the comparable cosine measure.
    assert by_id["v1-strong"]["relevance"] == 0.95
    assert by_id["v2-strong"]["relevance"] == 0.9
    # score_kind labels how to read the preserved raw score.
    assert by_id["v1-strong"]["score_kind"] == "l2_squared"
    assert by_id["v2-strong"]["score_kind"] == "cosine"


def test_v1_only_output_is_byte_identical_to_pre_feature() -> None:
    """R6 guard: a v1-only view (no scoreKind anywhere) must produce the EXACT
    pre-feature output — ascending raw-score order, ranks 1..N, and NO
    ``relevance``/``score_kind`` field added. Full result dicts are asserted."""
    raw = {
        "v1-a": {
            "collectionName": "v1-a",
            "results": [_chunk("worst", 3.0), _chunk("best", 0.1)],
        },
        "v1-b": {
            "collectionName": "v1-b",
            "results": [_chunk("mid", 1.0)],
        },
    }
    out = format_search_results_for_llm(raw, "q")

    # No cross-engine fields leak into a v1-only view.
    for r in out["results"]:
        assert "relevance" not in r
        assert "score_kind" not in r
        assert set(r) == _V1_CHUNK_KEYS

    # Exact ordering (ascending raw distance) + exact per-chunk dicts.
    assert out["results"] == [
        {
            "rank": 1,
            "relevance_score": 0.1,
            "collection": "v1-a",
            "document_id": "best",
            "document_url": "u/best",
            "chunk_number": 0,
            "text": "text for best",
        },
        {
            "rank": 2,
            "relevance_score": 1.0,
            "collection": "v1-b",
            "document_id": "mid",
            "document_url": "u/mid",
            "chunk_number": 0,
            "text": "text for mid",
        },
        {
            "rank": 3,
            "relevance_score": 3.0,
            "collection": "v1-a",
            "document_id": "worst",
            "document_url": "u/worst",
            "chunk_number": 0,
            "text": "text for worst",
        },
    ]
