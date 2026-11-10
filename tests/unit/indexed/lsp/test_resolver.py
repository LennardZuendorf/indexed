"""Definition resolution: exact spans, honest file-level fallback, nulls.

The three acceptance cases of the Tier 1 ``definition`` card live here: a hit
with a line span resolves to its indexed range, a span-less source degrades to a
range covering the whole document (never to an invented line/column), and an
unknown identifier answers ``null`` instead of a plausible-looking location.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from indexed.lsp import protocol
from indexed.lsp.resolver import (
    DEFINITION_MAX_CHUNKS,
    DEFINITION_MAX_DOCS,
    REFERENCES_LIMIT,
    REFERENCES_MAX_CHUNKS,
    REFERENCES_MAX_DOCS,
    chunk_location,
    document_range,
    identifier_at,
    matching_locations,
    resolve_definitions,
    resolve_references,
    word_at,
)
from indexed.lsp.server import LanguageServer

pytestmark = pytest.mark.unit

STATUS = SimpleNamespace(
    name="probe",
    source_type="localFiles",
    updated_time="2026-11-02T09:00:00+00:00",
)


class FakeBackend:
    """Records the one engine call a keystroke is allowed to make."""

    def __init__(
        self,
        *,
        results: Optional[Dict[str, Any]] = None,
        owning: Optional[Any] = STATUS,
        base: Optional[str] = None,
    ) -> None:
        self.results = results or {}
        self.owning = owning
        self.base = base
        self.searches: List[Dict[str, Any]] = []
        self.owner_queries: List[str] = []

    def statuses(self) -> List[Any]:
        return [STATUS]

    def status_for(self, name: str) -> Optional[Any]:
        return STATUS if name == STATUS.name else None

    def base_path(self, collection: str) -> Optional[str]:
        return self.base

    def collection_for_path(self, path: str) -> Optional[Any]:
        self.owner_queries.append(path)
        return self.owning

    def search(
        self,
        query: str,
        collection: Optional[str] = None,
        *,
        max_docs: int = 10,
        max_chunks: int = 30,
    ) -> Dict[str, Any]:
        self.searches.append(
            {
                "query": query,
                "collection": collection,
                "max_docs": max_docs,
                "max_chunks": max_chunks,
            }
        )
        return self.results


def _hit(
    path: Path,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    doc_url: Optional[str] = None,
) -> Dict[str, Any]:
    """One engine hit for ``path``, in the shape ``build_hover`` consumes."""
    return {
        "doc": {
            "id": str(path),
            "url": doc_url if doc_url is not None else f"file://{path}",
        },
        "chunk": {
            "chunkNumber": 1,
            "score": 0.4,
            "content": {"indexedData": text, "metadata": metadata or {}},
        },
    }


def _results(hits: List[Dict[str, Any]], collection: str = "probe") -> Dict[str, Any]:
    return {
        collection: {
            "collectionName": collection,
            "results": [
                {
                    "id": hit["doc"]["id"],
                    "url": hit["doc"]["url"],
                    "matchedChunks": [hit["chunk"]],
                }
                for hit in hits
            ],
        }
    }


def _server(backend: Any) -> LanguageServer:
    server = LanguageServer(backend, server_version="9.9.9")
    answer, _ = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert answer is not None
    return server


def _definition(server: LanguageServer, uri: str, line: int, character: int):
    return server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "textDocument/definition",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        }
    )


def _definitions(
    backend: Any, uri: str, position: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """The resolver called directly, so a test can assert the empty list."""
    return resolve_definitions(backend, uri, position)


def _references(server: LanguageServer, uri: str, line: int, character: int):
    """A ``textDocument/references`` request, with a client context attached."""
    return server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "textDocument/references",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": True},
            },
        }
    )


def _reference_list(
    backend: Any, uri: str, position: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """The plural resolver called directly, so a test can count past the cap."""
    return resolve_references(backend, uri, position)


# -- the cursor's identifier --------------------------------------------------


def test_identifier_at_reads_the_token_under_the_cursor(tmp_path) -> None:
    source = tmp_path / "a.py"
    source.write_text("def alpha():\n    return 1\n", encoding="utf-8")

    assert identifier_at(str(source), {"line": 0, "character": 5}) == "alpha"
    assert identifier_at(str(source), {"line": 1, "character": 6}) == "return"
    # The forgiving sibling hover uses still answers past the last token.
    assert word_at("alpha beta", 99) == "beta"


def test_identifier_at_is_strict_about_where_the_cursor_is(tmp_path) -> None:
    source = tmp_path / "a.py"
    source.write_text("    return 1\n", encoding="utf-8")

    # Indentation is not an identifier, and the line is not guessed at.
    assert identifier_at(str(source), {"line": 0, "character": 1}) is None
    assert identifier_at(str(source), {"line": 9, "character": 0}) is None
    assert identifier_at(str(source), {"line": 0, "character": -1}) is None
    assert identifier_at(str(source), {"line": True, "character": 0}) is None
    # An unreadable source has no line to take a word from.
    assert identifier_at(str(tmp_path), {"line": 0, "character": 0}) is None


# -- a hit with a span: the indexed range ------------------------------------


def test_definition_with_a_line_span_returns_the_indexed_range(tmp_path) -> None:
    target = tmp_path / "a.py"
    target.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    cursor = tmp_path / "b.py"
    cursor.write_text("from a import alpha\n", encoding="utf-8")

    backend = FakeBackend(
        results=_results(
            [
                _hit(
                    target,
                    f"# {target}\ndef alpha():\n    return 1",
                    {
                        "start_line": 0,
                        "end_line": 1,
                        "file_path": str(target),
                        "language": "python",
                    },
                )
            ]
        )
    )
    answer, _ = _definition(_server(backend), f"file://{cursor}", 0, 16)

    assert answer is not None
    assert answer["result"] == [
        {
            "uri": Path(target).as_uri(),
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 1, "character": 12},
            },
        }
    ]
    # One keyed, bounded query — the owning collection only, never the store.
    assert backend.searches == [
        {
            "query": "alpha",
            "collection": "probe",
            "max_docs": DEFINITION_MAX_DOCS,
            "max_chunks": DEFINITION_MAX_CHUNKS,
        }
    ]


# -- a span-less source: the whole document ----------------------------------


def test_definition_in_a_spanless_source_is_file_level(tmp_path) -> None:
    target = tmp_path / "guide.md"
    target.write_text("# Retrieval\n\nBody text.\n", encoding="utf-8")
    cursor = tmp_path / "a.py"
    cursor.write_text("see Retrieval\n", encoding="utf-8")

    backend = FakeBackend(
        results=_results(
            [
                _hit(
                    target,
                    f"{target}\n# Retrieval\n\nBody text.",
                    {"headings": ["Retrieval"], "file_path": str(target)},
                )
            ]
        )
    )
    answer, _ = _definition(_server(backend), f"file://{cursor}", 0, 6)

    assert answer is not None
    location = answer["result"][0]
    assert location["uri"] == Path(target).as_uri()
    # The document's own extent — 3 lines, exclusive end — not a fabricated
    # 0,0 position and not a guessed line inside the file.
    assert location["range"] == {
        "start": {"line": 0, "character": 0},
        "end": {"line": 3, "character": 0},
    }


def test_file_level_range_ends_inside_the_last_line_without_a_newline(tmp_path) -> None:
    target = tmp_path / "guide.md"
    target.write_text("# Retrieval\n\nBody text.", encoding="utf-8")

    backend = FakeBackend(
        results=_results(
            [_hit(target, "# Retrieval\nBody text.", {"headings": ["Retrieval"]})]
        )
    )
    cursor = tmp_path / "a.py"
    cursor.write_text("see Retrieval\n", encoding="utf-8")
    answer, _ = _definition(_server(backend), f"file://{cursor}", 0, 6)

    assert answer is not None
    assert answer["result"][0]["range"] == {
        "start": {"line": 0, "character": 0},
        "end": {"line": 2, "character": 10},
    }


def test_a_spanless_remote_source_yields_no_location(tmp_path) -> None:
    cursor = tmp_path / "a.py"
    cursor.write_text("see Retrieval\n", encoding="utf-8")
    backend = FakeBackend(
        results=_results(
            [
                _hit(
                    tmp_path / "unused.md",
                    "Retrieval",
                    {"headings": ["Retrieval"]},
                    doc_url="https://x.atlassian.net/wiki/spaces/ENG/pages/1/Retrieval",
                )
            ]
        )
    )
    answer, _ = _definition(_server(backend), f"file://{cursor}", 0, 6)

    assert answer is not None
    # No local document text to measure: `null` beats a fabricated position.
    assert answer["result"] is None


# -- honest nulls ------------------------------------------------------------


def test_unknown_identifier_returns_null(tmp_path) -> None:
    cursor = tmp_path / "a.py"
    cursor.write_text("gamma = 1\n", encoding="utf-8")
    backend = FakeBackend(results={})
    answer, _ = _definition(_server(backend), f"file://{cursor}", 0, 2)

    assert answer is not None
    assert answer["result"] is None
    assert backend.searches[0]["query"] == "gamma"


def test_a_longer_token_is_not_a_definition_of_the_identifier(tmp_path) -> None:
    target = tmp_path / "a.py"
    target.write_text("alphabet = 1\n", encoding="utf-8")
    cursor = tmp_path / "b.py"
    cursor.write_text("alpha\n", encoding="utf-8")
    backend = FakeBackend(
        results=_results(
            [_hit(target, "alphabet = 1", {"start_line": 0, "end_line": 0})]
        )
    )
    answer, _ = _definition(_server(backend), f"file://{cursor}", 0, 2)

    assert answer is not None
    assert answer["result"] is None


def test_a_cursor_off_an_identifier_searches_nothing(tmp_path) -> None:
    cursor = tmp_path / "a.py"
    cursor.write_text("    return 1\n", encoding="utf-8")
    backend = FakeBackend()
    answer, _ = _definition(_server(backend), f"file://{cursor}", 0, 1)

    assert answer is not None
    assert answer["result"] is None
    assert backend.searches == []


def test_a_file_no_collection_owns_returns_null(tmp_path) -> None:
    cursor = tmp_path / "a.py"
    cursor.write_text("alpha = 1\n", encoding="utf-8")
    backend = FakeBackend(owning=None)
    answer, _ = _definition(_server(backend), f"file://{cursor}", 0, 2)

    assert answer is not None
    assert answer["result"] is None
    assert backend.searches == []


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"textDocument": {}, "position": {"line": 0, "character": 0}},
        {"textDocument": {"uri": "file:///a.py"}},
    ],
)
def test_definition_rejects_bad_params(params) -> None:
    answer, _ = _server(FakeBackend()).handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "textDocument/definition",
            "params": params,
        }
    )
    assert answer is not None
    assert answer["error"]["code"] == protocol.INVALID_PARAMS


# -- the shared lookup the references card builds on -------------------------


def test_matching_locations_dedupes_the_same_span(tmp_path) -> None:
    target = tmp_path / "a.py"
    target.write_text("alpha = 1\n", encoding="utf-8")
    metadata = {"start_line": 0, "end_line": 0, "file_path": str(target)}
    hit = _hit(target, "alpha = 1", metadata)

    locations = matching_locations(_results([hit, hit, hit]), "alpha")

    assert len(locations) == 1


def test_matching_locations_enforces_the_cap(tmp_path) -> None:
    hits = []
    for index in range(4):
        target = tmp_path / f"m{index}.py"
        target.write_text("alpha = 1\n", encoding="utf-8")
        hits.append(
            _hit(
                target,
                "alpha = 1",
                {"start_line": 0, "end_line": 0, "file_path": str(target)},
            )
        )

    # Four distinguishable locations, two allowed: the cap is the answer's
    # size, not a filter applied after the fact.
    assert len(matching_locations(_results(hits), "alpha", limit=2)) == 2


def test_document_range_measures_the_file_and_refuses_the_unreadable(tmp_path) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")

    zero = {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}
    assert document_range(str(empty)) == zero
    # Nothing to measure (missing file, a directory): no range at all rather
    # than a made-up one.
    assert document_range(str(tmp_path / "missing.md")) is None
    assert document_range(str(tmp_path)) is None


def test_a_spanless_hit_whose_file_vanished_yields_no_location(tmp_path) -> None:
    cursor = tmp_path / "a.py"
    cursor.write_text("see Retrieval\n", encoding="utf-8")
    gone = tmp_path / "gone.md"
    backend = FakeBackend(
        results=_results([_hit(gone, "Retrieval", {"headings": ["Retrieval"]})])
    )

    assert _definitions(backend, f"file://{cursor}", {"line": 0, "character": 6}) == []


def test_a_hit_with_no_addressable_document_yields_no_location() -> None:
    assert chunk_location({"id": "x"}, {"content": "alpha"}) is None


def test_the_path_stub_chunk_is_never_a_definition() -> None:
    # Chunk 0 of every v1 document states the path and nothing else; a location
    # for it would navigate to the top of a file for no reason.
    hit = {"content": "alpha"}
    assert chunk_location({"id": "alpha"}, hit) is None


def test_matching_locations_skips_failed_collections_and_odd_docs() -> None:
    results = {
        "broken": {"error": "index unreadable"},
        "probe": {"results": ["not a document"]},
    }
    assert matching_locations(results, "alpha") == []


def test_resolve_definitions_ignores_non_file_uris() -> None:
    backend = FakeBackend()
    uri = "https://x.atlassian.net/wiki/spaces/ENG/pages/1/Retrieval"

    assert _definitions(backend, uri, {"line": 0, "character": 2}) == []
    assert backend.searches == []


# -- references: the same lookup, plural -------------------------------------


def test_references_across_files_are_all_returned(tmp_path) -> None:
    cursor = tmp_path / "use.py"
    cursor.write_text("alpha()\n", encoding="utf-8")
    first = tmp_path / "a.py"
    first.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    second = tmp_path / "b.py"
    second.write_text("from a import alpha\n", encoding="utf-8")
    noise = tmp_path / "c.py"
    noise.write_text("alphabet = 'abc'\n", encoding="utf-8")

    backend = FakeBackend(
        results=_results(
            [
                _hit(
                    first,
                    "def alpha():\n    return 1",
                    {"start_line": 0, "end_line": 1, "file_path": str(first)},
                ),
                _hit(
                    second,
                    "from a import alpha",
                    {"start_line": 0, "end_line": 0, "file_path": str(second)},
                ),
                # A semantic match, not a reference: "alphabet" is a different
                # token and gets no location.
                _hit(
                    noise,
                    "alphabet = 'abc'",
                    {"start_line": 0, "end_line": 0, "file_path": str(noise)},
                ),
            ]
        )
    )
    answer, _ = _references(_server(backend), f"file://{cursor}", 0, 2)

    assert answer is not None
    assert [location["uri"] for location in answer["result"]] == [
        first.as_uri(),
        second.as_uri(),
    ]
    # Still one keyed, bounded query — its own (wider) bounds, same collection.
    assert backend.searches == [
        {
            "query": "alpha",
            "collection": "probe",
            "max_docs": REFERENCES_MAX_DOCS,
            "max_chunks": REFERENCES_MAX_CHUNKS,
        }
    ]


def test_references_in_a_spanless_source_are_file_level(tmp_path) -> None:
    cursor = tmp_path / "use.py"
    cursor.write_text("see Retrieval\n", encoding="utf-8")
    guide = tmp_path / "guide.md"
    guide.write_text("# Retrieval\n\nBody text.\n", encoding="utf-8")
    backend = FakeBackend(
        results=_results(
            [
                _hit(
                    guide,
                    f"{guide}\n# Retrieval\n\nBody text.",
                    {"headings": ["Retrieval"], "file_path": str(guide)},
                )
            ]
        )
    )
    answer, _ = _references(_server(backend), f"file://{cursor}", 0, 6)

    assert answer is not None
    assert answer["result"] == [
        {
            "uri": guide.as_uri(),
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 3, "character": 0},
            },
        }
    ]


def test_references_cap_is_enforced(tmp_path) -> None:
    cursor = tmp_path / "use.py"
    cursor.write_text("alpha = 1\n", encoding="utf-8")
    hits = []
    for index in range(REFERENCES_LIMIT + 2):
        target = tmp_path / f"r{index}.py"
        target.write_text("alpha = 1\n", encoding="utf-8")
        hits.append(
            _hit(
                target,
                "alpha = 1",
                {"start_line": 0, "end_line": 0, "file_path": str(target)},
            )
        )

    # The default cap is the answer's size: the extra hits are never returned,
    # so the panel cannot grow without bound on a file with many uses.
    locations = _reference_list(
        FakeBackend(results=_results(hits)),
        f"file://{cursor}",
        {"line": 0, "character": 0},
    )

    assert len(locations) == REFERENCES_LIMIT


def test_no_references_is_an_empty_array_not_null(tmp_path) -> None:
    cursor = tmp_path / "a.py"
    cursor.write_text("alpha = 1\n", encoding="utf-8")
    answer, _ = _references(_server(FakeBackend()), f"file://{cursor}", 0, 2)

    # LSP: null is a protocol violation for references, [] is "none found".
    assert answer is not None
    assert answer["result"] == []


def test_references_rejects_bad_params() -> None:
    answer, _ = _server(FakeBackend()).handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "textDocument/references",
            "params": {"textDocument": {"uri": "file:///a.py"}},
        }
    )
    assert answer is not None
    assert answer["error"]["code"] == protocol.INVALID_PARAMS
