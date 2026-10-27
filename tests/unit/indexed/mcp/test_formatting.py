"""Unit tests for ``mcp.formatting.build_search_payload`` — the one machine shape.

The payload is documented in ``.spec/tech-app.md`` § Search result contract and typed in
``indexed.protocols.results`` (issues #108/#109). These tests pin the three
properties the shape exists for:

- documents state their own facts once (collection/source/id/url/score_kind),
  hits carry only relevance/score/locator/text;
- ranking is one comparable measure across v1 (squared-L2, lower better) and
  v2 (cosine/rerank, higher better);
- the locator is HONEST: a line span where lines exist, a page where pages
  exist, a heading path where only headings exist, and ``document`` where
  nothing is known — never an invented range.
"""

from __future__ import annotations

from indexed.mcp.formatting import V1_SCORE_KIND, build_locator, build_search_payload


def _doc(doc_id: str, score: float, **chunk) -> dict:
    """A matched document with one chunk; ``chunk`` overrides its content."""
    content = {"indexedData": f"text for {doc_id}"}
    content.update(chunk.pop("content", {}))
    return {
        "id": doc_id,
        "url": f"u/{doc_id}",
        "matchedChunks": [{"chunkNumber": 0, "score": score, "content": content}],
        **chunk,
    }


def _ids(payload: dict) -> list[str]:
    return [hit["text"] for doc in payload["documents"] for hit in doc["hits"]]


# --- ranking -----------------------------------------------------------------


def test_v1_lower_squared_l2_ranks_first() -> None:
    """v1 carries no ``scoreKind``: squared-L2 distance, lower is better."""
    raw = {"v1-coll": {"results": [_doc("worst", 3.0), _doc("best", 0.1)]}}
    payload = build_search_payload(raw, "q")

    assert _ids(payload) == ["text for best", "text for worst"]
    assert payload["documents"][0]["score_kind"] == V1_SCORE_KIND
    assert payload["documents"][0]["hits"][0]["score"] == 0.1


def test_v2_cosine_higher_ranks_first() -> None:
    raw = {
        "v2-coll": {
            "scoreKind": "cosine",
            "results": [_doc("worst", 0.02), _doc("best", 0.9)],
        }
    }
    payload = build_search_payload(raw, "q")

    assert _ids(payload) == ["text for best", "text for worst"]
    assert payload["documents"][0]["score_kind"] == "cosine"


def test_mixed_engines_rank_on_one_comparable_relevance() -> None:
    """A better v2 hit outranks a worse v1 hit and vice-versa — the ranking is
    not "v2 always first". l2 d²=0.1 -> rel 0.95; cosine 0.9 -> 0.9."""
    raw = {
        "v1-coll": {"results": [_doc("v1-strong", 0.1), _doc("v1-weak", 1.6)]},
        "v2-coll": {
            "scoreKind": "cosine",
            "results": [_doc("v2-strong", 0.9), _doc("v2-weak", 0.4)],
        },
    }
    payload = build_search_payload(raw, "q")

    assert _ids(payload) == [
        "text for v1-strong",
        "text for v2-strong",
        "text for v2-weak",
        "text for v1-weak",
    ]
    relevance = [
        hit["relevance"] for doc in payload["documents"] for hit in doc["hits"]
    ]
    assert relevance == [0.95, 0.9, 0.4, 0.2]


def test_reranked_collection_reports_real_score_kind_not_cosine() -> None:
    """issue #186: a consumer must see ``rerank``, not the higher-is-better
    bool collapsed into ``cosine``."""
    raw = {"v2-coll": {"scoreKind": "rerank", "results": [_doc("d1", 6.27)]}}
    payload = build_search_payload(raw, "q")

    assert payload["documents"][0]["score_kind"] == "rerank"
    assert payload["documents"][0]["hits"][0]["score"] == 6.27


def test_rerank_logit_lands_inside_the_unit_interval() -> None:
    """An unbounded rerank logit must not sit outside the [0,1] range a cosine
    relevance occupies when the two are ranked together (issue #186)."""
    raw = {
        "v2-cosine": {"scoreKind": "cosine", "results": [_doc("cos", 0.9)]},
        "v2-rerank": {"scoreKind": "rerank", "results": [_doc("rr", 6.27)]},
    }
    payload = build_search_payload(raw, "q")
    relevance = {
        hit["text"]: hit["relevance"] for d in payload["documents"] for hit in d["hits"]
    }

    assert 0.0 < relevance["text for rr"] < 1.0
    assert relevance["text for cos"] == 0.9


# --- grouping: document facts stated once ------------------------------------


def test_document_level_facts_are_stated_once_not_per_hit() -> None:
    """The old flat payload repeated collection/document_id/document_url on
    every chunk; the grouped payload states them once per document."""
    raw = {
        "coll": {
            "sourceType": "localFiles",
            "results": [
                {
                    "id": "d1",
                    "url": "file:///d1.py",
                    "matchedChunks": [
                        {
                            "chunkNumber": i,
                            "score": 0.1 * i,
                            "content": {"indexedData": f"c{i}"},
                        }
                        for i in (1, 2, 3)
                    ],
                }
            ],
        }
    }
    payload = build_search_payload(raw, "q")

    assert payload["counts"] == {"documents": 1, "hits": 3}
    doc = payload["documents"][0]
    assert doc["collection"] == "coll"
    assert doc["id"] == "d1"
    assert doc["source_type"] == "localFiles"
    for hit in doc["hits"]:
        assert set(hit) == {"relevance", "score", "locator", "text"}


def test_documents_are_ordered_by_their_best_hit() -> None:
    raw = {
        "coll": {
            "results": [
                {
                    "id": "worse",
                    "url": "u/w",
                    "matchedChunks": [
                        {
                            "chunkNumber": 0,
                            "score": 1.0,
                            "content": {"indexedData": "w"},
                        }
                    ],
                },
                {
                    "id": "better",
                    "url": "u/b",
                    "matchedChunks": [
                        {
                            "chunkNumber": 0,
                            "score": 0.2,
                            "content": {"indexedData": "b"},
                        }
                    ],
                },
            ]
        }
    }
    payload = build_search_payload(raw, "q")

    assert [d["id"] for d in payload["documents"]] == ["better", "worse"]


def test_document_without_url_or_source_type_omits_them() -> None:
    """Absent facts are omitted, not emitted as null/empty strings."""
    raw = {
        "coll": {
            "results": [
                {
                    "id": "d1",
                    "url": "",
                    "matchedChunks": [
                        {
                            "chunkNumber": 0,
                            "score": 0.5,
                            "content": {"indexedData": "x"},
                        }
                    ],
                }
            ]
        }
    }
    payload = build_search_payload(raw, "q")

    doc = payload["documents"][0]
    assert "url" not in doc
    assert "source_type" not in doc


def test_path_is_stated_once_on_the_document_not_per_hit() -> None:
    """A path on every hit is the boilerplate this shape removes: the document
    carries it, the hits carry only the range."""
    raw = {
        "coll": {
            "results": [
                {
                    "id": "a.py",
                    "url": "file:///repo/src/a.py",
                    "matchedChunks": [
                        {
                            "chunkNumber": i,
                            "score": 0.1 * i,
                            "content": {
                                "indexedData": f"chunk {i}",
                                "metadata": {
                                    "start_line": i,
                                    "end_line": i,
                                    "file_path": "/repo/src/a.py",
                                },
                            },
                        }
                        for i in (1, 2, 3)
                    ],
                }
            ]
        }
    }
    payload = build_search_payload(raw, "q")

    doc = payload["documents"][0]
    assert doc["path"] == "/repo/src/a.py"
    for hit in doc["hits"]:
        assert "path" not in hit["locator"]
        assert hit["locator"]["kind"] == "line_span"


def test_file_url_that_restates_the_path_is_dropped() -> None:
    """``url: file://<path>`` adds nothing the document already says."""
    raw = {
        "coll": {
            "results": [
                {
                    "id": "a.py",
                    "url": "file:///repo/a.py",
                    "matchedChunks": [
                        {
                            "chunkNumber": 0,
                            "score": 0.5,
                            "content": {
                                "indexedData": "x",
                                "metadata": {
                                    "start_line": 0,
                                    "end_line": 1,
                                    "file_path": "/repo/a.py",
                                },
                            },
                        }
                    ],
                }
            ]
        }
    }
    payload = build_search_payload(raw, "q")

    doc = payload["documents"][0]
    assert doc["path"] == "/repo/a.py"
    assert "url" not in doc


def test_url_that_adds_information_is_kept() -> None:
    """A Jira/Outline url says where to open the document — never dropped."""
    raw = {
        "coll": {
            "results": [
                {
                    "id": "T-1",
                    "url": "https://jira.example/browse/T-1",
                    "matchedChunks": [
                        {
                            "chunkNumber": 0,
                            "score": 0.5,
                            "content": {
                                "indexedData": "x",
                                "metadata": {"headings": ["Summary"]},
                            },
                        }
                    ],
                }
            ]
        }
    }
    payload = build_search_payload(raw, "q")

    assert payload["documents"][0]["url"] == "https://jira.example/browse/T-1"


# --- locator honesty ---------------------------------------------------------


def test_code_chunk_gets_a_one_based_line_span() -> None:
    """Code metadata is 0-based inclusive on disk; the locator is 1-based
    inclusive, matching what `grep -n` and every editor show."""
    locator = build_locator(
        {"start_line": 20, "end_line": 38, "file_path": "src/a.py"}, "file:///x/a.py"
    )

    assert locator == {
        "kind": "line_span",
        "path": "src/a.py",
        "start_line": 21,
        "end_line": 39,
    }


def test_line_span_falls_back_to_a_file_url_path() -> None:
    locator = build_locator({"start_line": 0, "end_line": 0}, "file:///repo/src/a.py")

    assert locator == {
        "kind": "line_span",
        "path": "/repo/src/a.py",
        "start_line": 1,
        "end_line": 1,
    }


def test_paginated_document_gets_a_page_locator() -> None:
    locator = build_locator({"page": 7, "headings": ["Intro"]}, "https://x/doc.pdf")

    assert locator == {"kind": "page", "page": 7}


def test_prose_document_gets_a_heading_path() -> None:
    locator = build_locator(
        {"headings": ["Search", "Output shape"]}, "file:///docs/search.md"
    )

    assert locator == {"kind": "headings", "headings": ["Search", "Output shape"]}


def test_chunk_without_any_position_says_document_not_a_fake_range() -> None:
    """The honesty constraint: Markdown/Jira/Confluence chunks that carry no
    line span and no headings must NOT invent a range."""
    assert build_locator({}, "https://jira.example/T-1") == {"kind": "document"}
    assert build_locator(None, "") == {"kind": "document"}
    # A partial pair (start without end) is not a range either.
    assert build_locator({"start_line": 4}, "file:///a.py") == {"kind": "document"}


def test_line_span_outranks_a_page_which_outranks_headings() -> None:
    both = {
        "start_line": 3,
        "end_line": 4,
        "file_path": "a.py",
        "page": 2,
        "headings": ["h"],
    }
    assert build_locator(both, "")["kind"] == "line_span"
    assert build_locator({"page": 2, "headings": ["h"]}, "")["kind"] == "page"
    assert build_locator({"headings": ["h"]}, "")["kind"] == "headings"


# --- text hygiene ------------------------------------------------------------


def test_code_context_prefix_is_stripped_when_the_locator_already_has_the_path() -> (
    None
):
    """The indexer prepends ``# <path>`` so the embedding sees it; the payload
    carries that path in locator.path, so the hit must not repeat it."""
    raw = {
        "coll": {
            "results": [
                {
                    "id": "a.py",
                    "url": "file:///a.py",
                    "matchedChunks": [
                        {
                            "chunkNumber": 1,
                            "score": 0.5,
                            "content": {
                                "indexedData": "# src/a.py\nprint(1)",
                                "metadata": {
                                    "start_line": 0,
                                    "end_line": 0,
                                    "file_path": "src/a.py",
                                },
                            },
                        }
                    ],
                }
            ]
        }
    }
    payload = build_search_payload(raw, "q")

    assert payload["documents"][0]["hits"][0]["text"] == "print(1)"


def test_text_prefix_is_kept_when_no_file_path_is_known() -> None:
    raw = {
        "coll": {
            "results": [
                {
                    "id": "d",
                    "url": "u",
                    "matchedChunks": [
                        {
                            "chunkNumber": 0,
                            "score": 0.5,
                            "content": {"indexedData": "# heading\nbody"},
                        }
                    ],
                }
            ]
        }
    }
    payload = build_search_payload(raw, "q")

    assert payload["documents"][0]["hits"][0]["text"] == "# heading\nbody"


# --- envelope ----------------------------------------------------------------


def test_envelope_carries_schema_counts_and_collections() -> None:
    raw = {
        "a": {"results": [_doc("d1", 0.1)]},
        "b": {"results": []},
    }
    payload = build_search_payload(raw, "hello")

    assert payload["schema"] == "indexed.search/1"
    assert payload["query"] == "hello"
    assert payload["counts"] == {"documents": 1, "hits": 1}
    assert payload["collections"] == ["a", "b"]
    assert payload["collection_errors"] == []


def test_failed_collection_is_reported_not_silently_empty() -> None:
    """E10: a failed collection must read as "index failed", never "0 matches"."""
    raw = {
        "broken": {"error": "index failed"},
        "good": {"results": [_doc("d1", 0.1)]},
    }
    payload = build_search_payload(raw, "q")

    assert payload["collection_errors"] == [
        {"collection": "broken", "error": "index failed"}
    ]
    assert payload["collections"] == ["good"]


def test_chunk_without_text_is_skipped() -> None:
    raw = {
        "coll": {
            "results": [
                {
                    "id": "d1",
                    "url": "u",
                    "matchedChunks": [
                        {
                            "chunkNumber": 0,
                            "score": 0.1,
                            "content": {"indexedData": ""},
                        },
                        {
                            "chunkNumber": 1,
                            "score": 0.2,
                            "content": {"indexedData": "real"},
                        },
                    ],
                }
            ]
        }
    }
    payload = build_search_payload(raw, "q")

    assert payload["counts"] == {"documents": 1, "hits": 1}
    assert payload["documents"][0]["hits"][0]["text"] == "real"


def test_empty_search_returns_the_envelope_with_no_documents() -> None:
    payload = build_search_payload({}, "q")

    assert payload["documents"] == []
    assert payload["counts"] == {"documents": 0, "hits": 0}
    assert payload["collection_errors"] == []
