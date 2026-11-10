"""The LSP stdio server.

A request/response loop over ``Content-Length``-framed JSON-RPC. The server
advertises only what is implemented and tested — ``textDocumentSync`` as
open/close/save notifications with no document content, ``workspace/symbol``,
``textDocument/hover``, ``textDocument/definition`` and
``textDocument/references`` — and answers everything else with the protocol's
``MethodNotFound`` instead of a plausible-looking empty result.

It also publishes ``textDocument/publishDiagnostics``, but only facts the index
can prove (see ``diagnostics.py``): a diagnostics channel that fabricates
warnings is worse than none (issue #241).
"""

from __future__ import annotations

import contextlib
import os
import sys
from typing import Any, BinaryIO, Dict, List, Optional, Set, Tuple

from loguru import logger

from . import protocol
from .backend import KnowledgeBackend
from .diagnostics import build_diagnostics
from .resolver import (
    IDENTIFIER,
    resolve_definitions,
    resolve_references,
    source_line,
    word_at,
)
from .results import build_hover, build_symbols, uri_to_path

SERVER_NAME = "indexed"

#: The server→client notification this server sends. Published only for facts
#: the index can prove, and emptied as soon as they stop being true.
PUBLISH_DIAGNOSTICS = "textDocument/publishDiagnostics"

#: Document lifecycle notifications. Handled, not ignored: they are the trigger
#: for diagnostics. ``textDocument/didChange`` is *not* in here — the server
#: advertises ``change: 0`` and reads the file from disk, so there is nothing
#: per-keystroke to do.
DOCUMENT_EVENTS = frozenset(
    {"textDocument/didOpen", "textDocument/didSave", "textDocument/didClose"}
)


class _InvalidParams(Exception):
    """Invalid request parameters (JSON-RPC ``-32602``)."""


#: Notifications the protocol allows us to ignore without implementing them.
IGNORED_METHODS = frozenset(
    {
        "initialized",
        "$/cancelRequest",
        "$/setTrace",
        "workspace/didChangeConfiguration",
        "workspace/didChangeWatchedFiles",
        "workspace/didChangeWorkspaceFolders",
        "textDocument/didChange",
        "window/workDoneProgress/cancel",
    }
)

#: Symbol palette answers are capped so one query cannot flood a client.
SYMBOL_LIMIT = 50


def _server_version() -> str:
    try:
        from importlib.metadata import version

        return version("indexed-sh")
    except Exception:  # noqa: BLE001 - a missing dist must not stop the server
        return "unknown"


def hover_query(uri: str, position: Dict[str, Any]) -> Optional[str]:
    """What to search for when hovering at a position.

    No document text is sent to the server — it advertises open/close/save
    notifications with no content (``change: 0``) — so the context comes from the
    file on disk, the one the user is looking at.
    """
    path = uri_to_path(uri)
    if path is None:
        # Only a document on disk can be read; a remote Jira/Confluence URI has
        # no local text to take the cursor's word from.
        return None

    line = position.get("line")
    character = position.get("character")
    if not isinstance(line, int) or isinstance(line, bool) or line < 0:
        return None
    if not isinstance(character, int) or isinstance(character, bool):
        character = 0

    text = source_line(path, line)
    if text is not None:
        word = word_at(text, character)
        if word is None:
            match = IDENTIFIER.search(text)
            word = match.group(0) if match else None
        if word:
            return word
        stripped = text.strip()
        if stripped:
            return stripped[:120]
    return os.path.splitext(os.path.basename(path))[0] or None


def _text_document_position(params: Any, method: str) -> Tuple[str, Dict[str, Any]]:
    """``textDocument.uri`` and ``position`` from request params, or -32602."""
    if not isinstance(params, dict):
        raise _InvalidParams(f"{method} requires an object")
    document = params.get("textDocument")
    uri = document.get("uri") if isinstance(document, dict) else None
    if not isinstance(uri, str) or not uri:
        raise _InvalidParams(f"{method} requires textDocument.uri")
    position = params.get("position")
    if not isinstance(position, dict):
        raise _InvalidParams(f"{method} requires a position")
    return uri, position


def _document_uri(params: Any) -> Optional[str]:
    """``textDocument.uri`` from notification params, or ``None`` when malformed."""
    document = params.get("textDocument") if isinstance(params, dict) else None
    uri = document.get("uri") if isinstance(document, dict) else None
    return uri if isinstance(uri, str) and uri else None


def _client_publishes_diagnostics(params: Any) -> bool:
    """Whether the client declared ``textDocument.publishDiagnostics``.

    An undeclared capability defaults to false in LSP, and an unsupported
    notification is one the client never agreed to receive — so an editor that
    did not ask gets silence instead of decorations it cannot render. (Every
    mainstream client declares it; the check exists so we do not assume.)
    """
    capabilities = params.get("capabilities") if isinstance(params, dict) else None
    document = (
        capabilities.get("textDocument") if isinstance(capabilities, dict) else None
    )
    if not isinstance(document, dict):
        return False
    declared = document.get("publishDiagnostics")
    return isinstance(declared, dict) or declared is True


class LanguageServer:
    """Stateful JSON-RPC dispatcher for one LSP session."""

    def __init__(
        self,
        backend: KnowledgeBackend,
        *,
        server_version: Optional[str] = None,
    ) -> None:
        self.backend = backend
        self.server_version = server_version or _server_version()
        self.initialized = False
        self.shutdown_requested = False
        #: Client declared `textDocument.publishDiagnostics` in `initialize`.
        self.client_publishes_diagnostics = False
        #: URIs we currently have published diagnostics for, so `didClose` can
        #: clear exactly those and nothing else.
        self.published: Set[str] = set()
        #: Server→client notifications queued by `handle`, drained by `serve`.
        self.pending_notifications: List[Dict[str, Any]] = []

    # -- lifecycle -----------------------------------------------------------

    def serve(self, reader: BinaryIO, writer: BinaryIO) -> int:
        """Read frames until ``exit``; return the process exit code."""
        while True:
            try:
                message = protocol.read_message(reader)
            except protocol.RpcError as exc:
                protocol.write_message(
                    writer, protocol.error_response(None, exc.code, exc.message)
                )
                if exc.fatal:
                    # An over-limit frame is refused before its body is read,
                    # so the rest of the stream cannot be framed correctly:
                    # ending beats answering the body's bytes as messages.
                    return 1
                continue
            if message is None:
                # The client went away without an `exit` notification.
                return 0 if self.shutdown_requested else 1
            # stdout belongs to the protocol: a stray `print` anywhere in the
            # engine would corrupt a frame, so anything that writes to
            # sys.stdout during dispatch is redirected to stderr.
            with contextlib.redirect_stdout(sys.stderr):
                answer, should_exit = self.handle(message)
            if answer is not None:
                protocol.write_message(writer, answer)
            for note in self.drain_notifications():
                protocol.write_message(writer, note)
            if should_exit:
                return 0 if self.shutdown_requested else 1

    def handle(self, message: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], bool]:
        """Answer one message; return ``(response, exit_requested)``."""
        has_id = "id" in message
        request_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            if has_id:
                return (
                    protocol.error_response(
                        request_id, protocol.INVALID_REQUEST, "missing method"
                    ),
                    False,
                )
            return None, False

        if method == "exit":
            return None, True

        if method == "initialize":
            if not has_id:
                # A notification must never be answered (JSON-RPC 2.0 §4.1),
                # and it must not start the session: the client's real
                # `initialize` would then be refused as a second one.
                return None, False
            if self.initialized:
                return (
                    protocol.error_response(
                        request_id,
                        protocol.INVALID_REQUEST,
                        "initialize may only be sent once",
                    ),
                    False,
                )
            self.initialized = True
            self.client_publishes_diagnostics = _client_publishes_diagnostics(
                message.get("params")
            )
            return protocol.response(request_id, self._capabilities()), False

        if not self.initialized:
            if not has_id:
                return None, False
            return (
                protocol.error_response(
                    request_id,
                    protocol.SERVER_NOT_INITIALIZED,
                    "initialize must be sent before any request",
                ),
                False,
            )

        if self.shutdown_requested:
            if not has_id:
                return None, False
            return (
                protocol.error_response(
                    request_id, protocol.INVALID_REQUEST, "server is shutting down"
                ),
                False,
            )

        if method == "shutdown":
            self.shutdown_requested = True
            if not has_id:
                # A shutdown notification is not a request: no response, but
                # the state change still stands (exit after it is clean).
                return None, False
            return protocol.response(request_id, None), False

        if method in DOCUMENT_EVENTS and not has_id:
            self._document_event(method, message.get("params"))
            return None, False

        if method in IGNORED_METHODS and not has_id:
            return None, False

        handler = {
            "workspace/symbol": self._workspace_symbol,
            "textDocument/hover": self._hover,
            "textDocument/definition": self._definition,
            "textDocument/references": self._references,
        }.get(method)
        if handler is None:
            if not has_id:
                return None, False
            return (
                protocol.error_response(
                    request_id,
                    protocol.METHOD_NOT_FOUND,
                    f"method not supported: {method}",
                ),
                False,
            )

        if not has_id:
            return None, False
        try:
            result = handler(message.get("params"))
        except _InvalidParams as exc:
            return (
                protocol.error_response(request_id, protocol.INVALID_PARAMS, str(exc)),
                False,
            )
        except Exception as exc:  # noqa: BLE001 - one bad request must not kill the session
            logger.opt(exception=exc).debug("LSP request {} failed", method)
            return (
                protocol.error_response(
                    request_id, protocol.INTERNAL_ERROR, f"{type(exc).__name__}: {exc}"
                ),
                False,
            )
        return protocol.response(request_id, result), False

    def _capabilities(self) -> Dict[str, Any]:
        """Only what is implemented and tested. Nothing is advertised empty."""
        return {
            "capabilities": {
                # Open/close/save notifications, no document content: the
                # server reads the file from disk and never holds a buffer, so
                # asking a client to stream every keystroke would be a promise
                # (`change`) it does not keep.
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
            "serverInfo": {"name": SERVER_NAME, "version": self.server_version},
        }

    # -- diagnostics (server → client) ---------------------------------------

    def drain_notifications(self) -> List[Dict[str, Any]]:
        """Take the queued server→client notifications (and empty the queue).

        ``handle`` stays a pure answer-or-nothing call so it remains testable
        without a pipe; the transport drains this after each message.
        """
        pending, self.pending_notifications = self.pending_notifications, []
        return pending

    def _document_event(self, method: str, params: Any) -> None:
        """Publish what the index can prove about one opened/saved/closed file.

        A notification gets no response (JSON-RPC 2.0 §4.1), so a malformed one
        is dropped rather than answered. A failing check is a debug log, never a
        dead session: an editor must not lose its language server because a
        diagnostics read went wrong.
        """
        uri = _document_uri(params)
        if uri is None:
            return
        if method == "textDocument/didClose":
            # Clear only what this session published; a file we never reported
            # on needs no empty republish.
            if uri in self.published:
                self._publish(uri, [])
            return
        try:
            diagnostics = build_diagnostics(self.backend, uri)
        except Exception as exc:  # noqa: BLE001 - never kill the session
            logger.opt(exception=exc).debug("LSP diagnostics failed for {}", uri)
            return
        self._publish(uri, diagnostics)

    def _publish(self, uri: str, diagnostics: List[Dict[str, Any]]) -> None:
        """Queue one ``publishDiagnostics``; an empty list clears what we set.

        An empty list is also published for a document this session never
        decorated, because that is what clears a leftover decoration from a
        previous session — the message is "this server has nothing to say about
        this document", which is true either way.
        """
        if not self.client_publishes_diagnostics:
            # The client did not declare support, so it never asked for this.
            return
        if diagnostics:
            self.published.add(uri)
        else:
            self.published.discard(uri)
        self.pending_notifications.append(
            protocol.notification(
                PUBLISH_DIAGNOSTICS, {"uri": uri, "diagnostics": diagnostics}
            )
        )

    # -- request handlers ----------------------------------------------------

    def _status_map(self, collection: Optional[str] = None) -> Dict[str, Any]:
        if collection is not None:
            status = self.backend.status_for(collection)
            return {collection: status} if status is not None else {}
        return {
            getattr(status, "name", ""): status for status in self.backend.statuses()
        }

    def _workspace_symbol(self, params: Any) -> Any:
        if not isinstance(params, dict):
            raise _InvalidParams("workspace/symbol requires an object with a query")
        query = params.get("query")
        if not isinstance(query, str):
            raise _InvalidParams("workspace/symbol requires a string 'query'")
        if not query.strip():
            return []
        results = self.backend.search(query, max_docs=20, max_chunks=60)
        return build_symbols(
            results, limit=SYMBOL_LIMIT, base_path_for=self.backend.base_path
        )

    def _hover(self, params: Any) -> Any:
        uri, position = _text_document_position(params, "textDocument/hover")

        query = hover_query(uri, position)
        if not query:
            return None

        # Scope the search to the collection that owns this file: hovering must
        # not reopen every collection on a keystroke (issue #126).
        status = None
        path = uri_to_path(uri)
        if path:
            status = self.backend.collection_for_path(path)
        if status is None:
            return None
        collection = getattr(status, "name", "")
        results = self.backend.search(query, collection, max_docs=3, max_chunks=9)
        return build_hover(results, self._status_map(collection), query)

    def _definition(self, params: Any) -> Any:
        """``Location[]`` for the identifier under the cursor, else ``null``.

        The resolver owns collection scoping and the file-level degradation, so
        this handler stays a parameter check. ``null`` — not ``[]`` — is LSP's
        "nothing defines this", and it is what an unknown identifier returns.
        """
        uri, position = _text_document_position(params, "textDocument/definition")
        return resolve_definitions(self.backend, uri, position) or None

    def _references(self, params: Any) -> Any:
        """``Location[]`` for the identifier under the cursor.

        Always an array, never ``null``: LSP reads an empty reference list as
        "none found" and ``null`` as a protocol violation, so the resolver's
        empty list is passed through as-is. ``context.includeDeclaration`` is
        accepted and ignored — the index holds chunks, not a symbol table, so
        there is no declaration bit to filter on, and returning the declaration
        among the references is the honest choice. The answer is bounded: one
        keyed query, its best hits (``resolver.REFERENCES_LIMIT``).
        """
        uri, position = _text_document_position(params, "textDocument/references")
        return resolve_references(self.backend, uri, position)


def serve(backend: KnowledgeBackend) -> int:
    """Run one stdio session on the process's real stdin/stdout."""
    return LanguageServer(backend).serve(sys.stdin.buffer, sys.stdout.buffer)


__all__ = [
    "DOCUMENT_EVENTS",
    "IGNORED_METHODS",
    "PUBLISH_DIAGNOSTICS",
    "SERVER_NAME",
    "SYMBOL_LIMIT",
    "LanguageServer",
    "hover_query",
    "serve",
    "uri_to_path",
]
