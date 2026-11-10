"""Dispatch tests for the LSP server: capabilities, errors, shutdown."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from indexed.lsp import protocol
from indexed.lsp.server import LanguageServer, hover_query, uri_to_path

pytestmark = pytest.mark.unit

STATUS = SimpleNamespace(
    name="probe",
    source_type="localFiles",
    updated_time="2026-11-02T09:00:00+00:00",
)


class FakeBackend:
    """A backend that records calls and returns canned engine output."""

    def __init__(
        self,
        *,
        results: Optional[Dict[str, Any]] = None,
        statuses: Optional[List[Any]] = None,
        owning: Optional[Any] = STATUS,
        raises: Optional[Exception] = None,
        base: Optional[str] = None,
    ) -> None:
        self.results = results or {}
        self._statuses = [STATUS] if statuses is None else statuses
        self.owning = owning
        self.raises = raises
        self.base = base
        self.searches: List[Dict[str, Any]] = []
        self.owner_queries: List[str] = []

    def statuses(self) -> List[Any]:
        return list(self._statuses)

    def status_for(self, name: str) -> Optional[Any]:
        return next((s for s in self._statuses if s.name == name), None)

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
        if self.raises is not None:
            raise self.raises
        return self.results


def _server(backend: Any) -> LanguageServer:
    return LanguageServer(backend, server_version="9.9.9")


def _initialize(server: LanguageServer) -> Dict[str, Any]:
    answer, _ = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert answer is not None
    return answer


def _call(server: LanguageServer, method: str, params: Any, request_id: int = 2):
    return server.handle(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )


def test_initialize_advertises_only_implemented_capabilities() -> None:
    answer = _initialize(_server(FakeBackend()))
    assert answer["result"] == {
        "capabilities": {
            "textDocumentSync": 0,
            "definitionProvider": True,
            "hoverProvider": True,
            "workspaceSymbolProvider": True,
        },
        "serverInfo": {"name": "indexed", "version": "9.9.9"},
    }


def test_request_before_initialize_is_refused() -> None:
    answer, _ = _call(_server(FakeBackend()), "workspace/symbol", {"query": "x"})
    assert answer is not None
    assert answer["error"]["code"] == protocol.SERVER_NOT_INITIALIZED


def test_notifications_before_initialize_are_ignored() -> None:
    answer, exit_requested = _server(FakeBackend()).handle(
        {"jsonrpc": "2.0", "method": "initialized", "params": {}}
    )
    assert answer is None
    assert exit_requested is False


def test_a_second_initialize_is_refused() -> None:
    """The LSP spec allows exactly one initialize per session."""
    server = _server(FakeBackend())
    _initialize(server)
    answer, _ = server.handle({"jsonrpc": "2.0", "id": 9, "method": "initialize"})
    assert answer is not None
    assert answer["error"]["code"] == protocol.INVALID_REQUEST


def test_unknown_request_returns_method_not_found() -> None:
    server = _server(FakeBackend())
    _initialize(server)
    answer, _ = _call(server, "textDocument/completion", {})
    assert answer is not None
    assert answer["error"] == {
        "code": protocol.METHOD_NOT_FOUND,
        "message": "method not supported: textDocument/completion",
    }


def test_unknown_notification_is_not_answered() -> None:
    server = _server(FakeBackend())
    _initialize(server)
    answer, exit_requested = server.handle(
        {"jsonrpc": "2.0", "method": "textDocument/formatting", "params": {}}
    )
    assert answer is None
    assert exit_requested is False


def test_message_without_a_method_is_refused() -> None:
    server = _server(FakeBackend())
    answer, _ = server.handle({"jsonrpc": "2.0", "id": 4})
    assert answer is not None
    assert answer["error"]["code"] == protocol.INVALID_REQUEST


def test_workspace_symbol_returns_hits_with_file_uris() -> None:
    results = {
        "probe": {
            "collectionName": "probe",
            "results": [
                {
                    "id": "a.py",
                    "url": "file:///repo/a.py",
                    "matchedChunks": [
                        {
                            "chunkNumber": 1,
                            "score": 0.4,
                            "content": {
                                "indexedData": "# /repo/a.py\ndef alpha():\n    return 1",
                                "metadata": {
                                    "start_line": 0,
                                    "end_line": 1,
                                    "file_path": "/repo/a.py",
                                    "node_type": "function_definition",
                                },
                            },
                        }
                    ],
                }
            ],
        }
    }
    backend = FakeBackend(results=results)
    server = _server(backend)
    _initialize(server)

    answer, _ = _call(server, "workspace/symbol", {"query": "alpha"})

    assert answer is not None
    assert answer["result"][0]["location"] == {
        "uri": "file:///repo/a.py",
        "range": {
            "start": {"line": 0, "character": 0},
            "end": {"line": 1, "character": 12},
        },
    }
    assert backend.searches == [
        {"query": "alpha", "collection": None, "max_docs": 20, "max_chunks": 60}
    ]


@pytest.mark.parametrize("params", [{}, {"query": 5}, None, []])
def test_workspace_symbol_rejects_bad_params(params) -> None:
    server = _server(FakeBackend())
    _initialize(server)
    answer, _ = _call(server, "workspace/symbol", params)
    assert answer is not None
    assert answer["error"]["code"] == protocol.INVALID_PARAMS


def test_workspace_symbol_with_a_blank_query_searches_nothing() -> None:
    backend = FakeBackend()
    server = _server(backend)
    _initialize(server)
    answer, _ = _call(server, "workspace/symbol", {"query": "   "})
    assert answer is not None
    assert answer["result"] == []
    assert backend.searches == []


def test_hover_searches_only_the_owning_collection(tmp_path) -> None:
    source = tmp_path / "a.py"
    source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    results = {
        "probe": {
            "collectionName": "probe",
            "results": [
                {
                    "id": "a.py",
                    "url": f"file://{source}",
                    "matchedChunks": [
                        {
                            "chunkNumber": 1,
                            "score": 0.4,
                            "content": {
                                "indexedData": f"# {source}\ndef alpha():\n    return 1",
                                "metadata": {
                                    "start_line": 0,
                                    "end_line": 1,
                                    "file_path": str(source),
                                    "language": "python",
                                },
                            },
                        }
                    ],
                }
            ],
        }
    }
    backend = FakeBackend(results=results)
    server = _server(backend)
    _initialize(server)

    answer, _ = _call(
        server,
        "textDocument/hover",
        {
            "textDocument": {"uri": f"file://{source}"},
            "position": {"line": 0, "character": 5},
        },
    )

    assert answer is not None
    value = answer["result"]["contents"]["value"]
    assert "def alpha():" in value
    assert "`probe`" in value
    assert "localFiles" in value
    assert "relevance " in value
    assert "query `alpha`" in value
    # Hover.range is in the hovered document — never claimed from another hit.
    assert "range" not in answer["result"]
    assert backend.owner_queries == [str(source)]
    assert backend.searches[0]["collection"] == "probe"
    assert backend.searches[0]["max_docs"] == 3


def test_hover_is_empty_when_no_collection_owns_the_file(tmp_path) -> None:
    source = tmp_path / "a.py"
    source.write_text("alpha = 1\n", encoding="utf-8")
    backend = FakeBackend(owning=None)
    server = _server(backend)
    _initialize(server)

    answer, _ = _call(
        server,
        "textDocument/hover",
        {
            "textDocument": {"uri": f"file://{source}"},
            "position": {"line": 0, "character": 2},
        },
    )

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
def test_hover_rejects_bad_params(params) -> None:
    server = _server(FakeBackend())
    _initialize(server)
    answer, _ = _call(server, "textDocument/hover", params)
    assert answer is not None
    assert answer["error"]["code"] == protocol.INVALID_PARAMS


def test_engine_failure_is_reported_without_killing_the_session() -> None:
    backend = FakeBackend(raises=RuntimeError("index unreadable"))
    server = _server(backend)
    _initialize(server)

    answer, _ = _call(server, "workspace/symbol", {"query": "alpha"})
    assert answer is not None
    assert answer["error"]["code"] == protocol.INTERNAL_ERROR
    assert "index unreadable" in answer["error"]["message"]

    backend.raises = None
    answer, _ = _call(server, "workspace/symbol", {"query": "alpha"}, request_id=3)
    assert answer is not None and answer["result"] == []


def test_shutdown_then_exit_is_clean() -> None:
    server = _server(FakeBackend())
    _initialize(server)

    answer, _ = server.handle({"jsonrpc": "2.0", "id": 2, "method": "shutdown"})
    assert answer == {"jsonrpc": "2.0", "id": 2, "result": None}

    answer, _ = _call(server, "workspace/symbol", {"query": "x"}, request_id=3)
    assert answer is not None
    assert answer["error"]["code"] == protocol.INVALID_REQUEST

    answer, exit_requested = server.handle({"jsonrpc": "2.0", "method": "exit"})
    assert answer is None
    assert exit_requested is True


def _frame(payload: Dict[str, Any]) -> bytes:
    body = json.dumps(payload).encode()
    return b"Content-Length: %d\r\n\r\n" % len(body) + body


def test_serve_drives_a_full_session_over_streams() -> None:
    session = b"".join(
        [
            _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            _frame({"jsonrpc": "2.0", "method": "initialized", "params": {}}),
            _frame({"jsonrpc": "2.0", "id": 2, "method": "shutdown"}),
            _frame({"jsonrpc": "2.0", "method": "exit"}),
        ]
    )
    out = io.BytesIO()
    assert _server(FakeBackend()).serve(io.BytesIO(session), out) == 0

    out.seek(0)
    first = protocol.read_message(out)
    second = protocol.read_message(out)
    assert first is not None and first["id"] == 1
    assert second is not None and second["id"] == 2
    assert protocol.read_message(out) is None


def test_serve_without_shutdown_exits_nonzero() -> None:
    session = _frame({"jsonrpc": "2.0", "method": "exit"})
    assert _server(FakeBackend()).serve(io.BytesIO(session), io.BytesIO()) == 1


def test_serve_answers_a_bad_frame_and_keeps_going() -> None:
    session = b"Content-Length: 3\r\n\r\nnop" + _frame(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    )
    out = io.BytesIO()
    assert _server(FakeBackend()).serve(io.BytesIO(session), out) == 1

    out.seek(0)
    error = protocol.read_message(out)
    assert error is not None
    assert error["error"]["code"] == protocol.PARSE_ERROR
    answer = protocol.read_message(out)
    assert answer is not None and answer["id"] == 1


def test_serve_ends_the_session_on_an_oversized_frame() -> None:
    """The body was never read: answering it as a frame would desync the stream."""
    oversized = b"Content-Length: %d\r\n\r\n" % (protocol.MAX_CONTENT_LENGTH + 1)
    session = (
        oversized
        + b"not-a-body"
        + _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    )
    out = io.BytesIO()
    assert _server(FakeBackend()).serve(io.BytesIO(session), out) == 1

    out.seek(0)
    error = protocol.read_message(out)
    assert error is not None
    assert error["error"]["code"] == protocol.INVALID_REQUEST
    # One answer, not a second bogus parse of the unread body.
    assert protocol.read_message(out) is None


def test_serve_never_answers_a_notification() -> None:
    """JSON-RPC 2.0 §4.1: a notification gets no response at all — not even
    ``id: null``, which is a ParseError's reserved id."""
    session = b"".join(
        [
            _frame({"jsonrpc": "2.0", "method": "initialize"}),
            _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            _frame({"jsonrpc": "2.0", "method": "exit"}),
        ]
    )
    out = io.BytesIO()
    assert _server(FakeBackend()).serve(io.BytesIO(session), out) == 1

    out.seek(0)
    answer = protocol.read_message(out)
    assert answer is not None and answer["id"] == 1
    assert protocol.read_message(out) is None


def test_initialize_as_a_notification_starts_nothing() -> None:
    server = _server(FakeBackend())
    answer, exit_requested = server.handle({"jsonrpc": "2.0", "method": "initialize"})

    assert answer is None
    assert exit_requested is False
    assert server.initialized is False
    # The client's real initialize still starts the session.
    assert _initialize(server)["result"]["capabilities"]["hoverProvider"] is True


def test_shutdown_as_a_notification_is_not_answered() -> None:
    server = _server(FakeBackend())
    _initialize(server)

    answer, exit_requested = server.handle({"jsonrpc": "2.0", "method": "shutdown"})

    assert answer is None
    assert exit_requested is False
    assert server.shutdown_requested is True


def test_workspace_symbol_resolves_a_relative_path_against_the_collection_base(
    tmp_path,
) -> None:
    base = tmp_path / "my corpus ü"
    base.mkdir()
    source = base / "sample file.py"
    source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    results = {
        "probe": {
            "results": [
                {
                    "id": "sample file.py",
                    "matchedChunks": [
                        {
                            "chunkNumber": 1,
                            "score": 0.4,
                            "content": {
                                "indexedData": "def alpha():\n    return 1",
                                "metadata": {
                                    "start_line": 0,
                                    "end_line": 1,
                                    "file_path": "sample file.py",
                                },
                            },
                        }
                    ],
                }
            ]
        }
    }
    server = _server(FakeBackend(results=results, base=str(base)))
    _initialize(server)

    answer, _ = _call(server, "workspace/symbol", {"query": "alpha"})

    assert answer is not None
    uri = answer["result"][0]["location"]["uri"]
    assert uri == source.as_uri()
    assert "%20" in uri and " " not in uri


def test_hover_query_reads_the_identifier_under_the_cursor(tmp_path) -> None:
    source = tmp_path / "a.py"
    source.write_text("def alpha():\n    return beta\n", encoding="utf-8")
    uri = f"file://{source}"

    assert hover_query(uri, {"line": 0, "character": 5}) == "alpha"
    assert hover_query(uri, {"line": 1, "character": 12}) == "beta"


def test_hover_query_falls_back_to_the_file_stem(tmp_path) -> None:
    source = tmp_path / "widget.py"
    source.write_text("1234\n", encoding="utf-8")
    assert hover_query(f"file://{source}", {"line": 9, "character": 0}) == "widget"


def test_hover_query_without_a_position_is_empty() -> None:
    assert hover_query("file:///a.py", {"line": -1}) is None


def test_hover_query_for_a_remote_uri_is_empty() -> None:
    assert (
        hover_query("https://x.atlassian.net/wiki/spaces/ENG/pages/1/Retrieval", {})
        is None
    )


def test_uri_to_path_leaves_non_file_uris_alone() -> None:
    assert uri_to_path("https://example.com/x") is None
    assert (
        uri_to_path("file:///tmp/nope-does-not-exist.py")
        == "/tmp/nope-does-not-exist.py"
    )
