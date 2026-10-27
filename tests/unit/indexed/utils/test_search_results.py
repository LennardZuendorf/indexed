"""The machine-readable search contract — ``indexed.search.v1`` (#108/#109).

These tests are the golden guard for the ONE shape both machine surfaces emit:
the CLI's ``indexed search --simple-output`` and the MCP ``search`` /
``search_collection`` tools. They fix three things the contract exists to
guarantee: an exact golden envelope, honest provenance (a locator only when the
chunk metadata supports it), and no per-hit boilerplate.

Ranking semantics are inherited and must not drift: a view containing a
higher-is-better engine (v2 cosine/rerank) ranks every hit on one comparable
``relevance`` measure, while a v1-only view keeps raw ascending squared-L2
distance and grows no ``relevance``/``score_kind`` field.
"""

from __future__ import annotations

import json

from indexed.protocols import SEARCH_OUTPUT_SCHEMA, SearchEnvelope
from indexed.utils.search_results import (
    build_search_envelope,
    chunk_locator,
    document_path,
    document_url,
)


def _v1_chunk(doc_id: str, score: float, **doc_fields) -> dict:
    return {
        "id": doc_id,
        "url": doc_fields.pop("url", f"u/{doc_id}"),
        **doc_fields,
        "matchedChunks": [
            {
                "chunkNumber": 0,
                "score": score,
                "content": {"indexedData": f"text for {doc_id}"},
            }
        ],
    }


def _hits(raw: dict, **kwargs) -> list[dict]:
    return build_search_envelope(raw, "q", **kwargs)["results"]


# --- ranking (inherited, must not drift) -------------------------------------


def test_v1_only_collection_sorts_ascending_lower_better() -> None:
    """No 'scoreKind' key at all (v1's real shape) — unchanged behaviour."""
    raw = {
        "v1-coll": {
            "collectionName": "v1-coll",
            "results": [_v1_chunk("worst", 3.0), _v1_chunk("best", 0.1)],
        }
    }
    hits = _hits(raw)
    assert [h["path"] for h in hits] == ["u/best", "u/worst"] or [
        h.get("path") for h in hits
    ] == [None, None]
    assert [h["text"] for h in hits] == ["text for best", "text for worst"]


def test_v2_cosine_sorts_descending_higher_better() -> None:
    raw = {
        "v2-coll": {
            "collectionName": "v2-coll",
            "scoreKind": "cosine",
            "results": [_v1_chunk("worst", 0.02), _v1_chunk("best", 0.9)],
        }
    }
    assert [h["text"] for h in _hits(raw)] == ["text for best", "text for worst"]


def test_mixed_v1_v2_ranks_on_one_comparable_relevance() -> None:
    """R11: with BOTH engines present, all chunks rank on one comparable
    measure — cosine, v1's squared-L2 mapped ``sim = 1 - d²/2`` — so a better
    v2 hit outranks a worse v1 hit and vice-versa (not 'v2 always first')."""
    raw = {
        # v1: squared-L2 distances (lower better). rel = 1 - d²/2.
        "v1-coll": {
            "collectionName": "v1-coll",
            "results": [_v1_chunk("v1-strong", 0.1), _v1_chunk("v1-weak", 1.6)],
        },
        # v2: cosine (higher better). rel = score.
        "v2-coll": {
            "collectionName": "v2-coll",
            "scoreKind": "cosine",
            "results": [_v1_chunk("v2-strong", 0.9), _v1_chunk("v2-weak", 0.4)],
        },
    }
    hits = _hits(raw)
    # relevances: v1-strong 0.95 > v2-strong 0.90 > v2-weak 0.40 > v1-weak 0.20
    assert [h["text"] for h in hits] == [
        "text for v1-strong",
        "text for v2-strong",
        "text for v2-weak",
        "text for v1-weak",
    ]
    by_text = {h["text"]: h for h in hits}
    # Each engine's RAW score is preserved untouched; relevance is comparable.
    assert by_text["text for v1-strong"]["score"] == 0.1
    assert by_text["text for v2-strong"]["score"] == 0.9
    assert by_text["text for v1-strong"]["relevance"] == 0.95
    assert by_text["text for v2-strong"]["relevance"] == 0.9
    # score_kind labels how to read the preserved raw score.
    assert by_text["text for v1-strong"]["score_kind"] == "l2_squared"
    assert by_text["text for v2-strong"]["score_kind"] == "cosine"


def test_reranked_collection_reports_real_score_kind_not_cosine() -> None:
    """issue #186: the kind must be the real one, not a boolean-derived guess."""
    raw = {
        "v2-coll": {
            "collectionName": "v2-coll",
            "scoreKind": "rerank",
            "results": [_v1_chunk("d1", 6.27)],
        }
    }
    hit = _hits(raw)[0]
    assert hit["score_kind"] == "rerank"
    assert hit["score"] == 6.27
    assert 0.0 < hit["relevance"] < 1.0


def test_unknown_score_kind_is_dropped_not_trusted() -> None:
    raw = {
        "weird": {
            "collectionName": "weird",
            "scoreKind": "future-kind",
            "results": [_v1_chunk("d1", 0.5)],
        }
    }
    hit = _hits(raw)[0]
    assert "score_kind" not in hit
    assert "relevance" not in hit


def test_v1_only_view_carries_no_cross_engine_fields() -> None:
    """R6 guard: a v1-only view must not grow ``relevance``/``score_kind``."""
    raw = {
        "v1-a": {
            "collectionName": "v1-a",
            "results": [_v1_chunk("worst", 3.0), _v1_chunk("best", 0.1)],
        }
    }
    for hit in _hits(raw):
        assert "relevance" not in hit
        assert "score_kind" not in hit


# --- golden envelope ---------------------------------------------------------


def _golden_raw() -> dict:
    return {
        "code": {
            "collectionName": "code",
            "indexerName": "all-MiniLM-L6-v2",
            "scoreKind": "cosine",
            "results": [
                {
                    "id": "src/indexed/config/service.py",
                    "url": "file:///repo/src/indexed/config/service.py",
                    "path": "file:///repo/src/indexed/config/service.py",
                    "matchedChunks": [
                        {
                            "chunkNumber": 2,
                            "score": 0.82,
                            "content": {
                                "indexedData": "def load_config() -> Config:",
                                "metadata": {
                                    "file_path": "src/indexed/config/service.py",
                                    "start_line": 9,
                                    "end_line": 41,
                                },
                            },
                        }
                    ],
                }
            ],
        },
        "notes": {
            "collectionName": "notes",
            # v1: no scoreKind key at all.
            "results": [
                {
                    "id": "notes/guide.md",
                    "url": "file:///repo/notes/guide.md",
                    "matchedChunks": [
                        {
                            "chunkNumber": 1,
                            "score": 0.4,
                            "content": {
                                "indexedData": "pip install indexed-sh",
                                "metadata": {"headings": ["Setup", "Install"]},
                            },
                        }
                    ],
                }
            ],
        },
        "plain": {
            "collectionName": "plain",
            "scoreKind": "cosine",
            "results": [
                {
                    "id": "d1",
                    "url": "",
                    "matchedChunks": [
                        {
                            "chunkNumber": 0,
                            "score": 0.3,
                            "content": {"indexedData": "bare"},
                        }
                    ],
                }
            ],
        },
        "broken": {"error": "index failed"},
    }


def _golden_expected() -> dict:
    return {
        "schema": "indexed.search.v1",
        "query": "how do I configure storage",
        "count": 3,
        "collections": {
            "code": "localFiles",
            "notes": "localFiles",
            "plain": "localFiles",
            "broken": "jira",
        },
        "collection_errors": [{"collection": "broken", "error": "index failed"}],
        "results": [
            {
                "collection": "code",
                "path": "src/indexed/config/service.py",
                "locator": {"lines": [10, 42]},
                "chunk": 2,
                "score": 0.82,
                "score_kind": "cosine",
                "relevance": 0.82,
                "text": "def load_config() -> Config:",
            },
            {
                "collection": "notes",
                "path": "/repo/notes/guide.md",
                "locator": {"headings": ["Setup", "Install"]},
                "chunk": 1,
                "score": 0.4,
                "score_kind": "l2_squared",
                "relevance": 0.8,
                "text": "pip install indexed-sh",
            },
            {
                "collection": "plain",
                "chunk": 0,
                "score": 0.3,
                "score_kind": "cosine",
                "relevance": 0.3,
                "text": "bare",
            },
        ],
    }


def test_golden_envelope_is_exact() -> None:
    envelope = build_search_envelope(
        _golden_raw(),
        "how do I configure storage",
        source_types={
            "code": "localFiles",
            "notes": "localFiles",
            "plain": "localFiles",
            "broken": "jira",
        },
    )
    assert envelope == _golden_expected()


def test_envelope_matches_the_documented_contract_model() -> None:
    """The emitted dict must validate against the contract #241/#222 import."""
    envelope = build_search_envelope(_golden_raw(), "q")
    validated = SearchEnvelope.model_validate(envelope)
    assert validated.schema_version == SEARCH_OUTPUT_SCHEMA
    assert validated.count == len(validated.results)
    # The published JSON schema is what documents the shape.
    schema = SearchEnvelope.model_json_schema()
    assert {"schema", "collections", "collection_errors", "results"} <= set(
        schema["properties"]
    )


def test_no_per_hit_boilerplate() -> None:
    """Rank is list position; source type is per collection, not per hit."""
    envelope = build_search_envelope(
        _golden_raw(), "q", source_types={"code": "localFiles"}
    )
    for hit in envelope["results"]:
        assert "rank" not in hit
        assert "source_type" not in hit
        assert "document_id" not in hit
        assert "document_url" not in hit
    assert envelope["collections"] == {"code": "localFiles"}


def test_unset_fields_are_omitted_not_null() -> None:
    envelope = build_search_envelope(_golden_raw(), "q")
    serialized = json.dumps(envelope)
    assert ":null" not in serialized
    assert "null" not in serialized
    # The `plain` hit knows nothing about where it lives — it says so by
    # omission, and it is still a hit (never silently dropped).
    plain = [h for h in envelope["results"] if h["collection"] == "plain"][0]
    assert set(plain) == {"collection", "chunk", "score", "score_kind", "relevance", "text"}


def test_failed_collection_is_never_reported_as_zero_matches() -> None:
    envelope = build_search_envelope({"broken": {"error": "index failed"}}, "q")
    assert envelope["count"] == 0
    assert envelope["collection_errors"] == [
        {"collection": "broken", "error": "index failed"}
    ]


def test_chunk_without_text_is_still_a_hit() -> None:
    """The old formatter dropped content-free chunks; identity is still useful."""
    raw = {
        "c": {
            "collectionName": "c",
            "scoreKind": "cosine",
            "results": [
                {
                    "id": "src/a.py",
                    "url": "file:///repo/src/a.py",
                    "matchedChunks": [{"chunkNumber": 0, "score": 0.9}],
                }
            ],
        }
    }
    hit = _hits(raw)[0]
    assert hit["path"] == "/repo/src/a.py"
    assert "text" not in hit


# --- provenance honesty ------------------------------------------------------


def test_locator_converts_recorded_zero_based_span_to_one_based() -> None:
    assert chunk_locator({"start_line": 0, "end_line": 0}) == {"lines": [1, 1]}
    assert chunk_locator({"start_line": 9, "end_line": 41}) == {"lines": [10, 42]}


def test_locator_prefers_lines_then_headings_then_page() -> None:
    both = {"start_line": 3, "end_line": 4, "headings": ["A"], "page": 7}
    assert chunk_locator(both) == {"lines": [4, 5]}
    assert chunk_locator({"headings": ["A", "B"], "page": 7}) == {"headings": ["A", "B"]}
    assert chunk_locator({"page": 7}) == {"page": 7}


def test_locator_is_absent_when_metadata_cannot_place_the_evidence() -> None:
    """The card's honesty constraint: no invented range, no invented page."""
    assert chunk_locator(None) is None
    assert chunk_locator({}) is None
    assert chunk_locator({"format": ".md", "size": 120}) is None
    # Malformed span (end before start) is not a location either.
    assert chunk_locator({"start_line": 9, "end_line": 3}) is None
    # Booleans are ints in Python; they are not line numbers.
    assert chunk_locator({"start_line": True, "end_line": True}) is None


def test_document_path_ignores_v1_internal_storage_path() -> None:
    """v1's ``path`` is ``documents/<id>.json`` — never a locator an agent uses."""
    assert document_path({"id": "d1", "path": "documents/d1.json", "url": "u/d1"}) is None
    assert (
        document_path({"id": "d1", "path": "documents/d1.json", "url": "file:///r/a.md"})
        == "/r/a.md"
    )


def test_document_path_prefers_recorded_file_path() -> None:
    assert (
        document_path(
            {"id": "x", "url": "file:///repo/src/a.py", "path": "file:///repo/src/a.py"},
            {"file_path": "src/a.py"},
        )
        == "src/a.py"
    )


def test_document_url_never_fabricates_and_never_duplicates_a_path() -> None:
    assert document_url({"url": "/doc/relative"}, None, "outline") is None
    assert document_url({"url": "https://x.atlassian.net/browse/A-1"}, None, "jira") == (
        "https://x.atlassian.net/browse/A-1"
    )
    # A file:// URL is dropped when the path already names the same place.
    assert document_url({"url": "file:///repo/a.md"}, "/repo/a.md", "localFiles") is None
    # ... and kept when it is the only location the hit has.
    assert document_url({"url": "file:///repo/a.md"}, None, "localFiles") == (
        "file:///repo/a.md"
    )
