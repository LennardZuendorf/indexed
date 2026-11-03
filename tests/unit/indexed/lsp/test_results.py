"""Golden-output tests for LSP symbols and hover.

The expected values are HAND-WRITTEN files (``golden/``), not snapshots of the
implementation: they are the contract, so a behaviour change has to disagree
with something a human wrote.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from indexed.lsp.results import (
    build_hover,
    build_symbols,
    document_uri,
    hit_text,
    is_path_chunk,
    lsp_range,
)
from indexed.mcp.formatting import build_locator as mcp_build_locator
from indexed.utils.provenance import build_locator, chunk_parts, strip_context_prefix

pytestmark = pytest.mark.unit

GOLDEN = Path(__file__).parent / "golden"

#: One v1 collection carrying the two locator kinds the LSP can render: a code
#: chunk (line span) and a Markdown chunk (heading path). Chunk 0 is the path
#: stub and must never become a symbol.
RAW_RESULTS = {
    "indexed-src": {
        "collectionName": "indexed-src",
        "indexerName": "e5-small",
        "sourceType": "localFiles",
        "results": [
            {
                "id": "src/indexed/utils/relevance.py",
                "url": "file:///repo/src/indexed/utils/relevance.py",
                "matchedChunks": [
                    {
                        "chunkNumber": 0,
                        "score": 0.9,
                        "content": {"indexedData": "src/indexed/utils/relevance.py"},
                    },
                    {
                        "chunkNumber": 1,
                        "score": 0.75,
                        "content": {
                            "indexedData": (
                                "# /repo/src/indexed/utils/relevance.py\n"
                                "def unified_relevance(raw_score, score_kind):\n"
                                "    return 1.0\n"
                            ),
                            "metadata": {
                                "language": "python",
                                "node_type": "function_definition",
                                "start_line": 20,
                                "end_line": 22,
                                "file_path": "/repo/src/indexed/utils/relevance.py",
                            },
                        },
                    },
                ],
            },
            {
                "id": "docs/notes.md",
                "url": "file:///repo/docs/notes.md",
                "matchedChunks": [
                    {
                        "chunkNumber": 1,
                        "score": 0.5,
                        "content": {
                            "indexedData": (
                                "Retrieval Notes > Scoring\n"
                                "Scores are unified across engines.\n"
                            ),
                            "metadata": {"headings": ["Retrieval Notes", "Scoring"]},
                        },
                    }
                ],
            },
        ],
    }
}

STATUSES = {
    "indexed-src": SimpleNamespace(
        name="indexed-src",
        source_type="localFiles",
        updated_time="2026-11-02T09:00:00+00:00",
    )
}

NOW = datetime(2026, 11, 2, 11, 30, tzinfo=timezone.utc)

#: A plaintext hit. The plaintext chunker prefixes these with the BARE path
#: (no ``# ``), unlike code chunks — a prefix the normaliser used to miss.
PLAINTEXT_RESULTS = {
    "txtprobe": {
        "collectionName": "txtprobe",
        "results": [
            {
                "id": "runbooks/deploy steps.txt",
                "url": "file:///repo/runbooks/deploy steps.txt",
                "matchedChunks": [
                    {
                        "chunkNumber": 1,
                        "score": 0.5,
                        "content": {
                            "indexedData": (
                                "/repo/runbooks/deploy steps.txt\n"
                                "Rollback runbook\n"
                                "Run it twice, then page on-call."
                            ),
                            "metadata": {
                                "file_path": "/repo/runbooks/deploy steps.txt"
                            },
                        },
                    }
                ],
            }
        ],
    }
}

TXT_STATUSES = {
    "txtprobe": SimpleNamespace(
        name="txtprobe",
        source_type="localFiles",
        updated_time="2026-11-02T09:00:00+00:00",
    )
}


def test_symbols_match_the_golden_payload() -> None:
    symbols = build_symbols(RAW_RESULTS)
    expected = json.loads((GOLDEN / "symbols.json").read_text(encoding="utf-8"))
    assert symbols == expected


def test_hover_matches_the_golden_markdown() -> None:
    hover = build_hover(RAW_RESULTS, STATUSES, "unified_relevance", now=NOW)
    assert hover is not None
    expected = (GOLDEN / "hover.md").read_text(encoding="utf-8")
    assert hover["contents"] == {"kind": "markdown", "value": expected}
    # LSP defines Hover.range in the HOVERED document; the top hit may live
    # elsewhere, so claiming a range here would underline unrelated text.
    assert "range" not in hover


@pytest.mark.parametrize(
    "updated_time, expected",
    [
        (None, "at an unknown time"),
        ("not-a-timestamp", "at not-a-timestamp"),
        ("2026-11-02T11:30:30+00:00", "just now"),
        ("2026-11-02T11:29:00+00:00", "1 minute ago"),
        ("2026-11-02T11:05:00+00:00", "25 minutes ago"),
        ("2026-11-02T09:00:00+00:00", "2 hours ago"),
        ("2026-11-02T11:00:00", "30 minutes ago"),
        ("2026-10-30T10:00:00+00:00", "3 days ago"),
        ("2026-10-01T10:00:00+00:00", "on 2026-10-01"),
        ("2026-11-02T12:00:00+00:00", "just now"),
    ],
)
def test_hover_freshness_is_a_readable_age(updated_time, expected) -> None:
    statuses = {
        "indexed-src": SimpleNamespace(
            name="indexed-src", source_type="localFiles", updated_time=updated_time
        )
    }
    hover = build_hover(RAW_RESULTS, statuses, "unified_relevance", now=NOW)
    assert hover is not None
    assert f"indexed {expected}" in hover["contents"]["value"]


def test_hover_returns_none_when_the_index_says_nothing() -> None:
    assert build_hover({}, STATUSES, "nothing") is None
    failed = {"broken": {"error": "collection could not be read"}}
    assert build_hover(failed, STATUSES, "nothing") is None


def test_hover_names_the_source_type_as_unknown_when_the_manifest_is_silent() -> None:
    statuses = {"indexed-src": SimpleNamespace(name="indexed-src", source_type=None)}
    hover = build_hover(RAW_RESULTS, statuses, "unified_relevance", now=NOW)
    assert hover is not None
    assert "· unknown ·" in hover["contents"]["value"]


def test_symbols_stop_at_the_limit() -> None:
    assert len(build_symbols(RAW_RESULTS, limit=1)) == 1


def test_symbols_skip_collections_that_failed() -> None:
    results = dict(RAW_RESULTS)
    results["broken"] = {"error": "collection could not be read"}
    assert build_symbols(results) == build_symbols(RAW_RESULTS)


@pytest.mark.parametrize(
    "metadata, doc_url, expected",
    [
        (
            {"start_line": 0, "end_line": 2, "file_path": "/a.py"},
            "file:///a.py",
            {"kind": "line_span", "path": "/a.py", "start_line": 1, "end_line": 3},
        ),
        (
            {"start_line": 5, "end_line": 5},
            "file:///a.py",
            {"kind": "line_span", "path": "/a.py", "start_line": 6, "end_line": 6},
        ),
        (
            {"page": 4},
            "file:///a.pdf",
            {"kind": "page", "page": 4, "path": "/a.pdf"},
        ),
        (
            {"page": 4, "file_path": "/a.pdf"},
            "file:///a.pdf",
            {"kind": "page", "page": 4, "path": "/a.pdf"},
        ),
        (
            {"headings": ["A", "", "B"]},
            "file:///a.md",
            {"kind": "headings", "headings": ["A", "B"]},
        ),
        ({"headings": ["", " "]}, "file:///a.md", {"kind": "document"}),
        ({}, "file:///a.txt", {"kind": "document"}),
        ({}, "https://example.atlassian.net/wiki/x", {"kind": "document"}),
    ],
)
def test_lsp_locators_come_from_the_shared_builder(metadata, doc_url, expected) -> None:
    """The LSP has no locator logic of its own — it uses the payload builder."""
    assert mcp_build_locator is build_locator
    assert build_locator(metadata, doc_url) == expected


def test_range_is_zero_based_and_ends_at_the_indexed_line_end() -> None:
    text = "def alpha():\n    return 1"
    assert lsp_range(text, {"start_line": 4, "end_line": 5}) == {
        "start": {"line": 4, "character": 0},
        "end": {"line": 5, "character": 12},
    }


def test_range_collapses_for_chunks_without_a_line_span() -> None:
    zero = {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}
    assert lsp_range("prose", {"headings": ["A"]}) == zero
    assert lsp_range("prose", {"start_line": 3}) == zero


def test_hit_text_strips_the_embedder_prefix_only() -> None:
    text, metadata = hit_text(
        {
            "content": {
                "indexedData": "# /a.py\ndef f():\n    pass",
                "metadata": {"file_path": "/a.py"},
            }
        }
    )
    assert text == "def f():\n    pass"
    assert metadata == {"file_path": "/a.py"}


def test_plaintext_context_prefix_is_stripped_from_symbols_and_hover() -> None:
    """Plaintext chunks embed the bare path; a symbol name must not BE a path."""
    assert (
        hit_text(
            {
                "content": {
                    "indexedData": "/a.txt\nbody",
                    "metadata": {"file_path": "/a.txt"},
                }
            }
        )[0]
        == "body"
    )

    symbols = build_symbols(PLAINTEXT_RESULTS)
    assert [s["name"] for s in symbols] == ["Rollback runbook"]

    hover = build_hover(PLAINTEXT_RESULTS, TXT_STATUSES, "rollback", now=NOW)
    assert hover is not None
    value = hover["contents"]["value"]
    assert "```\nRollback runbook\n" in value
    assert "/repo/runbooks/deploy steps.txt" not in value
    # The URI still names the file — percent-encoded, so it is a real URI.
    assert symbols[0]["location"]["uri"] == "file:///repo/runbooks/deploy%20steps.txt"


def test_chunk_parts_keeps_a_text_only_chunk() -> None:
    """A string ``content`` is a real hit; dropping it would hide search results."""
    assert chunk_parts({"content": "plain string"}) == ("plain string", {})
    assert chunk_parts({}) == ("", {})
    assert strip_context_prefix("plain", {}) == "plain"


def test_path_chunk_detection() -> None:
    doc = {"id": "src/a.py"}
    assert is_path_chunk("src/a.py", {}, doc) is True
    assert is_path_chunk("def f():\n    pass", {}, doc) is False
    assert is_path_chunk("", {}, doc) is True


def test_document_uri_prefers_a_real_scheme_and_falls_back_to_the_file() -> None:
    assert (
        document_uri({"url": "https://x.atlassian.net/browse/A-1"})
        == "https://x.atlassian.net/browse/A-1"
    )
    assert document_uri({"url": "file:///repo/a.py"}) == "file:///repo/a.py"
    assert document_uri({"url": ""}, {"file_path": "/repo/b.py"}) == "file:///repo/b.py"


def test_document_uri_percent_encodes_spaces_and_non_ascii(tmp_path) -> None:
    """A raw ``file://`` concat is not a URI; strict clients reject it."""
    folder = tmp_path / "my corpus ü" / "nested dir"
    folder.mkdir(parents=True)
    source = folder / "sample file.py"
    source.write_text("x = 1\n", encoding="utf-8")
    expected = source.as_uri()
    assert "%20" in expected and " " not in expected

    # The connector's hand-built url, a chunk's file_path, and an already
    # encoded url all land on the same valid URI.
    assert document_uri({"url": f"file://{source}"}) == expected
    assert document_uri({"url": ""}, {"file_path": str(source)}) == expected
    assert document_uri({"url": expected}) == expected


def test_relative_file_path_resolves_against_the_collection_base(tmp_path) -> None:
    """Never the server process's cwd: that belongs to the editor."""
    base = tmp_path / "corpus"
    base.mkdir()
    source = base / "a b.py"
    source.write_text("print(1)\n", encoding="utf-8")

    assert (
        document_uri({"url": ""}, {"file_path": "a b.py"}, base_path=str(base))
        == source.as_uri()
    )

    symbols = build_symbols(
        {
            "probe": {
                "results": [
                    {
                        "id": "a b.py",
                        "matchedChunks": [
                            {
                                "chunkNumber": 1,
                                "score": 0.5,
                                "content": {
                                    "indexedData": "print(1)",
                                    "metadata": {
                                        "file_path": "a b.py",
                                        "start_line": 0,
                                        "end_line": 0,
                                    },
                                },
                            }
                        ],
                    }
                ]
            }
        },
        base_path_for=lambda collection: str(base),
    )
    assert symbols[0]["location"]["uri"] == source.as_uri()
