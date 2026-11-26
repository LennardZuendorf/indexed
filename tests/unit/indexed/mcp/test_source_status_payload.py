"""``sources`` — the per-source record on the ``indexed.search/1`` payload.

The card these tests belong to exists because of one failure: a source that is
disabled, empty or gone used to leave *no trace* in the payload, so "two sources
answered" and "three sources were meant to, one died" looked identical. Every
test here pins one half of that distinction at the builder, which is the one
place CLI and MCP share.
"""

from __future__ import annotations

import json

import pytest

from indexed.mcp.formatting import build_search_payload
from indexed.protocols.results import SEARCH_SCHEMA

pytestmark = pytest.mark.unit


def _answered(name: str, *, source_type: str = "localFiles", documents: int = 1):
    """One collection the engine answered for, with one matching chunk each."""
    return {
        "collectionName": name,
        "indexerName": "default",
        "sourceType": source_type,
        "results": [
            {
                "id": f"{name}/doc-1",
                "url": f"file:///repo/{name}/doc-1.md",
                "matchedChunks": [
                    {
                        "chunkNumber": 1,
                        "score": 0.5,
                        "content": {
                            "indexedData": f"answer in {name}",
                            "metadata": {"headings": ["Answers"]},
                        },
                    }
                ],
            }
        ],
    }


def _declare(name, *, status=None, source_type=None, documents=None, error=None):
    declaration = {"collection": name}
    if status is not None:
        declaration["status"] = status
    if source_type is not None:
        declaration["source_type"] = source_type
    if documents is not None:
        declaration["documents"] = documents
    if error is not None:
        declaration["error"] = error
    return declaration


def _sources(payload):
    return {entry["collection"]: entry for entry in payload["sources"]}


def test_three_sources_answer_and_each_is_listed_ok() -> None:
    raw = {
        "gh-issues": _answered("gh-issues", source_type="github"),
        "wiki": _answered("wiki"),
        "src": _answered("src"),
    }
    sources = [_declare(name) for name in ("gh-issues", "wiki", "src")]

    payload = build_search_payload(raw, "q", sources=sources)

    assert payload["schema"] == SEARCH_SCHEMA
    assert payload["collections"] == ["gh-issues", "wiki", "src"]
    assert [entry["status"] for entry in payload["sources"]] == ["ok", "ok", "ok"]
    assert payload["counts"] == {"documents": 3, "hits": 3}


def test_a_declared_source_the_engine_never_saw_is_missing_not_silence() -> None:
    raw = {"gh-issues": _answered("gh-issues"), "wiki": _answered("wiki")}
    sources = [
        _declare("gh-issues"),
        _declare("wiki"),
        _declare(
            "src",
            status="missing",
            error="Workspace definition '/repo/indexed.toml' selects collection "
            "'src', which is not in the store at '/store'.",
        ),
    ]

    payload = build_search_payload(raw, "q", sources=sources)

    listed = _sources(payload)
    assert listed["src"]["status"] == "missing"
    assert "not in the store" in listed["src"]["error"]
    # The dead source is not claimed as searched, and the payload still names it.
    assert "src" not in payload["collections"]
    assert [entry["collection"] for entry in payload["collection_errors"]] == ["src"]
    assert payload["counts"]["documents"] == 2


def test_a_failed_source_keeps_the_engine_error_and_the_rest() -> None:
    raw = {
        "src": {"error": "No FAISS index found at /store/src/indexes/default"},
        "wiki": _answered("wiki"),
    }

    payload = build_search_payload(
        raw, "q", sources=[_declare("src"), _declare("wiki")]
    )

    assert _sources(payload)["src"] == {
        "collection": "src",
        "status": "failed",
        "error": "No FAISS index found at /store/src/indexes/default",
    }
    # Exactly one verdict, stated once in each view — not duplicated.
    assert payload["collection_errors"] == [
        {
            "collection": "src",
            "error": "No FAISS index found at /store/src/indexes/default",
        }
    ]
    assert payload["counts"]["hits"] == 1


def test_an_undeclared_failed_source_is_a_source_not_silence() -> None:
    """MCP without a selection and CLI ``--collection`` declare no scope.

    The engine still failed a collection it was handed; that failure must be a
    ``sources`` record, not a ``collection_errors`` entry with no source beside
    it (#340 review).
    """
    payload = build_search_payload({"src": {"error": "boom"}}, "q")

    assert payload["sources"] == [
        {"collection": "src", "status": "failed", "error": "boom"}
    ]
    assert payload["collection_errors"] == [{"collection": "src", "error": "boom"}]
    # A failed source was not searched.
    assert payload["collections"] == []


def test_an_empty_collection_is_not_a_zero_hit_match() -> None:
    """R3 — the red condition: zero documents must never read as "no match"."""
    raw = {"wiki": {"collectionName": "wiki", "results": []}}

    payload = build_search_payload(
        raw,
        "q",
        sources=[_declare("wiki", documents=0), _declare("src")],
    )

    listed = _sources(payload)
    assert listed["wiki"]["status"] == "empty"
    assert listed["wiki"]["documents"] == 0
    assert "indexes no documents" in listed["wiki"]["error"]
    # An empty source answered nothing, so it is not a searched collection —
    # the docs' contract: a non-`ok` source is never in `collections`.
    assert "wiki" not in payload["collections"]
    assert any(
        entry["collection"] == "wiki" and "indexes no documents" in entry["error"]
        for entry in payload["collection_errors"]
    )


def test_an_unusable_collection_is_named() -> None:
    payload = build_search_payload(
        {},
        "q",
        sources=[
            _declare(
                "notes",
                status="unusable",
                error="Collection 'notes' has no usable index; re-index it.",
            )
        ],
    )

    assert payload["sources"] == [
        {
            "collection": "notes",
            "status": "unusable",
            "error": "Collection 'notes' has no usable index; re-index it.",
        }
    ]
    assert payload["counts"] == {"documents": 0, "hits": 0}


def test_an_undeclared_answered_collection_is_appended_as_ok() -> None:
    """``sources`` is always a superset of ``collections`` — never a smaller list."""
    raw = {"docs": _answered("docs"), "notes": _answered("notes")}

    payload = build_search_payload(raw, "q", sources=[_declare("docs")])

    assert [entry["collection"] for entry in payload["sources"]] == ["docs", "notes"]
    assert all(entry["status"] == "ok" for entry in payload["sources"])


def test_without_a_declared_scope_the_answered_collections_are_the_sources() -> None:
    raw = {"docs": _answered("docs")}

    payload = build_search_payload(raw, "q")

    assert [entry["collection"] for entry in payload["sources"]] == ["docs"]
    assert payload["sources"][0]["status"] == "ok"


def test_an_undeclared_empty_index_is_empty_not_ok() -> None:
    """No declarations (CLI ``--collection``): the opened index is the witness.

    The declaration loop is not the only place a source can be empty. With no
    declared scope the engine's own ``indexSize`` is the only statement that
    "there was nothing to match", and it must produce the same verdict — a
    zero-hit ``ok`` here is exactly the silent failure #340 exists to prevent.
    """
    raw = {"wiki": {"collectionName": "wiki", "indexSize": 0, "results": []}}

    payload = build_search_payload(raw, "q")

    assert payload["sources"] == [
        {
            "collection": "wiki",
            "status": "empty",
            "documents": 0,
            "error": (
                "Collection 'wiki' indexes no documents, so nothing can match; "
                "re-run indexing for it."
            ),
        }
    ]
    assert payload["collections"] == []
    assert payload["collection_errors"] == [
        {
            "collection": "wiki",
            "error": (
                "Collection 'wiki' indexes no documents, so nothing can match; "
                "re-run indexing for it."
            ),
        }
    ]


def test_an_undeclared_empty_index_does_not_hide_beside_an_ok_source() -> None:
    """The undeclared path keeps each sibling's own verdict and ordering."""
    raw = {
        "wiki": {"collectionName": "wiki", "indexSize": 0, "results": []},
        "docs": _answered("docs"),
    }

    payload = build_search_payload(raw, "q")

    listed = _sources(payload)
    assert listed["wiki"]["status"] == "empty"
    assert listed["docs"]["status"] == "ok"
    assert payload["collections"] == ["docs"]
    assert [error["collection"] for error in payload["collection_errors"]] == ["wiki"]


def test_sources_are_additive_and_the_shape_stays_small() -> None:
    """R6 — the key is new; nothing else about the documented shape moved."""
    raw = {"docs": _answered("docs")}

    payload = build_search_payload(raw, "q", sources=[_declare("docs")])

    assert list(payload) == [
        "schema",
        "query",
        "counts",
        "collections",
        "collection_errors",
        "sources",
        "documents",
    ]
    # A source record is a handful of scalars: it may not carry text, hits or
    # a copy of the documents block.
    assert len(json.dumps(payload["sources"])) < 400


def test_a_hit_can_name_the_comment_it_came_from() -> None:
    """An issue comment hit resolves to the comment, not just to the issue."""
    raw = {
        "gh-issues": {
            "collectionName": "gh-issues",
            "sourceType": "github",
            "results": [
                {
                    "id": "acme/widget#7",
                    "url": "https://github.com/acme/widget/issues/7",
                    "matchedChunks": [
                        {
                            "chunkNumber": 2,
                            "score": 0.4,
                            "content": {
                                "indexedData": "Comment by dev: the answer is 42",
                                "metadata": {
                                    "commentId": "IC_kwDO123",
                                    "commentUrl": (
                                        "https://github.com/acme/widget/issues/7"
                                        "#issuecomment-987"
                                    ),
                                },
                            },
                        }
                    ],
                }
            ],
        }
    }

    document = build_search_payload(raw, "q")["documents"][0]

    assert document["url"] == "https://github.com/acme/widget/issues/7"
    assert document["hits"][0]["url"].endswith("#issuecomment-987")
