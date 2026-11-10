"""LSP base-protocol framing over stdio.

The Language Server Protocol frames each JSON-RPC message with
``Content-Length: <bytes>\\r\\n\\r\\n`` headers and a UTF-8 JSON body. That is
*not* the newline-delimited framing the MCP stdio transport uses, so it is
implemented here rather than reused from ``indexed.mcp``.

Kept deliberately small and I/O-only: the server, not the wire, decides what a
message means.
"""

from __future__ import annotations

import json
from typing import Any, BinaryIO, Dict, Optional

# JSON-RPC 2.0 error codes plus the LSP-specific "not initialized" code.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
SERVER_NOT_INITIALIZED = -32002

#: Upper bound on one frame's declared body. The server never receives document
#: text (open/close/save notifications only, ``change: 0``), so anything this
#: large is a broken or hostile peer; refusing beats blocking on a read that
#: will never finish.
MAX_CONTENT_LENGTH = 8 * 1024 * 1024


class RpcError(Exception):
    """A frame that could not be decoded.

    The caller answers it with ``code``/``message`` and keeps serving — except
    when ``fatal`` is set: an over-limit ``Content-Length`` leaves a body in the
    stream that was never read, so the remaining bytes cannot be framed
    correctly and the session ends instead of answering the body as messages.
    """

    def __init__(self, code: int, message: str, *, fatal: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.fatal = fatal


def read_message(stream: BinaryIO) -> Optional[Dict[str, Any]]:
    """Read one framed message, or ``None`` at end of stream.

    Raises ``RpcError`` for a frame that is present but undecodable: the caller
    answers it and keeps serving, so one bad frame cannot kill the session.
    """
    headers: Dict[bytes, bytes] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        stripped = line.strip()
        if not stripped:
            break
        if b":" in stripped:
            key, value = stripped.split(b":", 1)
            headers[key.strip().lower()] = value.strip()

    raw_length = headers.get(b"content-length")
    if raw_length is None:
        raise RpcError(PARSE_ERROR, "missing Content-Length header")
    try:
        length = int(raw_length)
    except ValueError as exc:
        raise RpcError(PARSE_ERROR, f"invalid Content-Length: {raw_length!r}") from exc
    if length < 0:
        raise RpcError(PARSE_ERROR, f"invalid Content-Length: {raw_length!r}")
    if length > MAX_CONTENT_LENGTH:
        # Refused before the body is read, so this frame is unrecoverable: the
        # declared body stays in the stream and would be parsed as headers.
        raise RpcError(
            INVALID_REQUEST,
            f"Content-Length {length} exceeds the {MAX_CONTENT_LENGTH}-byte limit",
            fatal=True,
        )

    body = stream.read(length)
    if len(body) < length:
        # The peer went away mid-frame. Nothing valid can follow, so this is a
        # decode failure rather than a clean EOF.
        raise RpcError(INVALID_REQUEST, "truncated message body")
    try:
        message = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RpcError(PARSE_ERROR, f"invalid JSON body: {exc}") from exc
    if not isinstance(message, dict):
        raise RpcError(INVALID_REQUEST, "message must be a JSON object")
    return message


def write_message(stream: BinaryIO, message: Dict[str, Any]) -> None:
    """Write one framed message and flush it (clients block on a short read)."""
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    stream.write(b"Content-Length: %d\r\n\r\n" % len(body))
    stream.write(body)
    stream.flush()


def response(request_id: Any, result: Any) -> Dict[str, Any]:
    """A successful JSON-RPC response (``result`` may be ``None``)."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    """A JSON-RPC error response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def notification(method: str, params: Any = None) -> Dict[str, Any]:
    """A server-to-client notification."""
    message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        message["params"] = params
    return message


__all__ = [
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "MAX_CONTENT_LENGTH",
    "PARSE_ERROR",
    "SERVER_NOT_INITIALIZED",
    "RpcError",
    "error_response",
    "notification",
    "read_message",
    "response",
    "write_message",
]
