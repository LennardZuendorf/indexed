"""Dispatch tests for the LSP server: capabilities, errors, shutdown."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from indexed.lsp import protocol
from indexed.lsp.diagnostics import NOT_IN_COLLECTION, SEVERITY_INFORMATION, STALE
from indexed.lsp.server import (
    PUBLISH_DIAGNOSTICS,
    LanguageServer,
    hover_query,
    uri_to_path,
)
from indexed.utils.fingerprint import file_fingerprint

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
        digest: Optional[str] = None,
        digest_raises: Optional[Exception] = None,
    ) -> None:
        self.results = results or {}
        self._statuses = [STATUS] if statuses is None else statuses
        self.owning = owning
        self.raises = raises
        self.base = base
        self.digest = digest
        self.digest_raises = digest_raises
        self.searches: List[Dict[str, Any]] = []
        self.owner_queries: List[str] = []
        self.digest_queries: List[tuple[str, str]] = []

    def statuses(self) -> List[Any]:
        return list(self._statuses)

    def status_for(self, name: str) -> Optional[Any]:
        return next((s for s in self._statuses if s.name == name), None)

    def base_path(self, collection: str) -> Optional[str]:
        return self.base

    def collection_for_path(self, path: str) -> Optional[Any]:
        self.owner_queries.append(path)
        return self.owning

    def indexed_digest(self, collection: str, path: str) -> Optional[str]:
        self.digest_queries.append((collection, path))
        if self.digest_raises is not None:
            raise self.digest_raises
        return self.digest

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
            # Open/close/save only: the server keeps no document state, so it
            # must not ask for `change` content it would throw away.
            "textDocumentSync": {
                "openClose": True,
                "change": 0,
                "save": {"includeText": False},
            },
            "definitionProvider": True,
            "hoverProvider": True,
            "referencesProvider": True,
            "workspaceSymbolProvider": True,
        },
        "serverInfo": {"name": "indexed", "version": "9.9.9"},
    }


def test_pull_diagnostics_are_not_advertised_because_they_are_not_implemented() -> None:
    """`diagnosticProvider` is pull diagnostics — a method this server refuses."""
    capabilities = _initialize(_server(FakeBackend()))["result"]["capabilities"]
    assert "diagnosticProvider" not in capabilities


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


# -- diagnostics (server → client) -------------------------------------------

#: A client that declared publishDiagnostics support, as every real editor does.
DIAGNOSTIC_CLIENT = {"capabilities": {"textDocument": {"publishDiagnostics": {}}}}


def _diagnostic_server(backend: Any, *, client_supports: bool = True) -> LanguageServer:
    server = _server(backend)
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": DIAGNOSTIC_CLIENT if client_supports else {"capabilities": {}},
        }
    )
    return server


def _notify(server: LanguageServer, method: str, uri: str) -> List[Dict[str, Any]]:
    """Send a document lifecycle notification; return what the server queued."""
    answer, exit_requested = server.handle(
        {
            "jsonrpc": "2.0",
            "method": method,
            "params": {"textDocument": {"uri": uri}},
        }
    )
    assert answer is None, "a notification must never be answered"
    assert exit_requested is False
    return server.drain_notifications()


def test_did_open_publishes_an_empty_array_for_a_healthy_file(tmp_path) -> None:
    path = tmp_path / "healthy.py"
    path.write_text("value = 1\n", encoding="utf-8")
    fingerprint = file_fingerprint(str(path))
    assert fingerprint is not None
    server = _diagnostic_server(FakeBackend(digest=fingerprint[0]))

    notifications = _notify(server, "textDocument/didOpen", path.as_uri())

    assert notifications == [
        {
            "jsonrpc": "2.0",
            "method": PUBLISH_DIAGNOSTICS,
            "params": {"uri": path.as_uri(), "diagnostics": []},
        }
    ]
    # Draining is what stops the same notification being sent twice.
    assert server.drain_notifications() == []


def test_a_stale_file_publishes_one_diagnostic_and_a_reindex_clears_it(
    tmp_path,
) -> None:
    path = tmp_path / "stale.py"
    path.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    backend = FakeBackend(digest="0000000000000000")
    server = _diagnostic_server(backend)

    published = _notify(server, "textDocument/didOpen", path.as_uri())
    assert len(published) == 1
    params = published[0]["params"]
    assert params["uri"] == path.as_uri()
    assert len(params["diagnostics"]) == 1
    diagnostic = params["diagnostics"][0]
    assert diagnostic["code"] == STALE
    assert diagnostic["severity"] == SEVERITY_INFORMATION
    assert diagnostic["range"] == {
        "start": {"line": 0, "character": 0},
        "end": {"line": 2, "character": 0},
    }
    assert backend.digest_queries == [("probe", str(path))]

    # The user runs `indexed index update probe`: the recorded digest matches
    # again, so the next save must clear the diagnostic, not just stay quiet.
    fingerprint = file_fingerprint(str(path))
    assert fingerprint is not None
    backend.digest = fingerprint[0]
    cleared = _notify(server, "textDocument/didSave", path.as_uri())
    assert [n["params"]["diagnostics"] for n in cleared] == [[]]
    assert server.published == set()


def test_a_file_no_collection_owns_publishes_the_not_in_collection_diagnostic(
    tmp_path,
) -> None:
    path = tmp_path / "loose.py"
    path.write_text("value = 1\n", encoding="utf-8")
    backend = FakeBackend(owning=None)
    server = _diagnostic_server(backend)

    published = _notify(server, "textDocument/didOpen", path.as_uri())

    diagnostics = published[0]["params"]["diagnostics"]
    assert [d["code"] for d in diagnostics] == [NOT_IN_COLLECTION]
    assert backend.digest_queries == []


def test_a_client_that_did_not_declare_support_gets_no_notification(
    tmp_path,
) -> None:
    path = tmp_path / "stale.py"
    path.write_text("value = 1\n", encoding="utf-8")
    server = _diagnostic_server(FakeBackend(digest="stale"), client_supports=False)

    assert _notify(server, "textDocument/didOpen", path.as_uri()) == []
    assert server.published == set()


def test_did_close_clears_only_what_was_actually_published(tmp_path) -> None:
    reported = tmp_path / "stale.py"
    reported.write_text("value = 1\n", encoding="utf-8")
    untouched = tmp_path / "other.py"
    untouched.write_text("value = 2\n", encoding="utf-8")
    server = _diagnostic_server(FakeBackend(digest="stale"))

    _notify(server, "textDocument/didOpen", reported.as_uri())
    assert _notify(server, "textDocument/didClose", untouched.as_uri()) == []

    closed = _notify(server, "textDocument/didClose", reported.as_uri())
    assert closed[0]["params"] == {"uri": reported.as_uri(), "diagnostics": []}


def test_document_notifications_before_initialize_publish_nothing(tmp_path) -> None:
    path = tmp_path / "stale.py"
    path.write_text("value = 1\n", encoding="utf-8")
    server = _server(FakeBackend(digest="stale"))
    server.client_publishes_diagnostics = True

    assert _notify(server, "textDocument/didOpen", path.as_uri()) == []


def test_a_failing_diagnostics_check_does_not_kill_the_session(tmp_path) -> None:
    path = tmp_path / "stale.py"
    path.write_text("value = 1\n", encoding="utf-8")
    server = _diagnostic_server(
        FakeBackend(digest_raises=RuntimeError("state.json is on fire"))
    )

    assert _notify(server, "textDocument/didOpen", path.as_uri()) == []

    # The session still answers requests and still exits cleanly.
    answer, _ = _call(server, "workspace/symbol", {"query": "alpha"})
    assert answer is not None and "result" in answer
    assert server.handle({"jsonrpc": "2.0", "method": "exit"}) == (None, True)
