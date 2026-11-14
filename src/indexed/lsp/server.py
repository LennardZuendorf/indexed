"""The LSP stdio server.

A request/response loop over ``Content-Length``-framed JSON-RPC. Tier 0
advertises only what is implemented and tested — ``textDocumentSync: 0`` (no
document state), ``workspace/symbol`` and ``textDocument/hover``; everything
else is answered with the protocol's ``MethodNotFound`` instead of a
plausible-looking empty result.
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
from typing import Any, BinaryIO, Dict, Optional, Tuple

from loguru import logger

from . import protocol
from .backend import KnowledgeBackend
from .results import build_hover, build_symbols, uri_to_path

SERVER_NAME = "indexed"


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
        "textDocument/didOpen",
        "textDocument/didChange",
        "textDocument/didClose",
        "textDocument/didSave",
        "window/workDoneProgress/cancel",
    }
)

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: Symbol palette answers are capped so one query cannot flood a client.
SYMBOL_LIMIT = 50


def _server_version() -> str:
    try:
        from importlib.metadata import version

        return version("indexed-sh")
    except Exception:  # noqa: BLE001 - a missing dist must not stop the server
        return "unknown"


def _source_line(path: str, line: int) -> Optional[str]:
    """The ``line``th line of ``path`` (0-based), read only as far as needed."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, text in enumerate(handle):
                if number == line:
                    return text.rstrip("\n")
    except OSError:
        return None
    return None


def _word_at(text: str, character: int) -> Optional[str]:
    """The identifier the cursor sits on (or just after), if any."""
    best: Optional[str] = None
    for match in _IDENTIFIER.finditer(text):
        if match.start() <= character <= match.end():
            return match.group(0)
        if match.end() <= character:
            best = match.group(0)
    return best


def hover_query(uri: str, position: Dict[str, Any]) -> Optional[str]:
    """What to search for when hovering at a position.

    No document text is sent to a Tier 0 server (no ``textDocumentSync``), so
    the context comes from the file on disk — the one the user is looking at.
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

    text = _source_line(path, line)
    if text is not None:
        word = _word_at(text, character)
        if word is None:
            match = _IDENTIFIER.search(text)
            word = match.group(0) if match else None
        if word:
            return word
        stripped = text.strip()
        if stripped:
            return stripped[:120]
    return os.path.splitext(os.path.basename(path))[0] or None


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

        if method in IGNORED_METHODS and not has_id:
            return None, False

        handler = {
            "workspace/symbol": self._workspace_symbol,
            "textDocument/hover": self._hover,
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
                "textDocumentSync": 0,
                "hoverProvider": True,
                "workspaceSymbolProvider": True,
            },
            "serverInfo": {"name": SERVER_NAME, "version": self.server_version},
        }

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
        if not isinstance(params, dict):
            raise _InvalidParams("textDocument/hover requires an object")
        document = params.get("textDocument")
        uri = document.get("uri") if isinstance(document, dict) else None
        if not isinstance(uri, str) or not uri:
            raise _InvalidParams("textDocument/hover requires textDocument.uri")
        position = params.get("position")
        if not isinstance(position, dict):
            raise _InvalidParams("textDocument/hover requires a position")

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


def serve(backend: KnowledgeBackend) -> int:
    """Run one stdio session on the process's real stdin/stdout."""
    return LanguageServer(backend).serve(sys.stdin.buffer, sys.stdout.buffer)


__all__ = [
    "IGNORED_METHODS",
    "SERVER_NAME",
    "SYMBOL_LIMIT",
    "LanguageServer",
    "hover_query",
    "serve",
    "uri_to_path",
]
