"""Framing tests for the LSP base protocol (Content-Length headers)."""

from __future__ import annotations

import io
import json

import pytest

from indexed.lsp import protocol

pytestmark = pytest.mark.unit


def _read_one(body: bytes) -> dict:
    stream = io.BytesIO(body)
    message = protocol.read_message(stream)
    assert message is not None
    return message


def test_write_message_frames_with_content_length_and_flushes() -> None:
    stream = io.BytesIO()
    protocol.write_message(stream, {"jsonrpc": "2.0", "id": 1, "result": None})

    raw = stream.getvalue()
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "result": None}, separators=(",", ":")
    ).encode()
    assert raw == b"Content-Length: %d\r\n\r\n" % len(body) + body


def test_read_message_parses_a_framed_body() -> None:
    body = b'{"jsonrpc":"2.0","id":7,"method":"initialize"}'
    message = _read_one(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    assert message == {"jsonrpc": "2.0", "id": 7, "method": "initialize"}


def test_read_message_accepts_lowercase_and_extra_headers() -> None:
    body = b'{"jsonrpc":"2.0","method":"exit"}'
    frame = (
        b"content-length: %d\r\nContent-Type: application/vscode-jsonrpc\r\n\r\n"
        % len(body)
    )
    assert _read_one(frame + body) == {"jsonrpc": "2.0", "method": "exit"}


def test_read_message_returns_none_at_eof() -> None:
    assert protocol.read_message(io.BytesIO(b"")) is None


def test_read_message_rejects_a_truncated_body() -> None:
    with pytest.raises(protocol.RpcError) as excinfo:
        protocol.read_message(io.BytesIO(b"Content-Length: 40\r\n\r\n{}"))
    assert excinfo.value.code == protocol.INVALID_REQUEST
    assert "truncated" in excinfo.value.message


def test_read_message_rejects_an_oversized_frame() -> None:
    header = b"Content-Length: %d\r\n\r\n" % (protocol.MAX_CONTENT_LENGTH + 1)
    with pytest.raises(protocol.RpcError) as excinfo:
        protocol.read_message(io.BytesIO(header))
    assert excinfo.value.code == protocol.INVALID_REQUEST
    assert "exceeds" in excinfo.value.message
    # Fatal: the body was never read, so the stream cannot be resynchronised.
    assert excinfo.value.fatal is True


def test_read_message_rejects_a_missing_content_length() -> None:
    with pytest.raises(protocol.RpcError) as excinfo:
        protocol.read_message(io.BytesIO(b"Content-Type: application/json\r\n\r\n{}"))
    assert excinfo.value.code == protocol.PARSE_ERROR


def test_read_message_rejects_a_non_numeric_length() -> None:
    with pytest.raises(protocol.RpcError) as excinfo:
        protocol.read_message(io.BytesIO(b"Content-Length: many\r\n\r\n{}"))
    assert excinfo.value.code == protocol.PARSE_ERROR


def test_read_message_rejects_invalid_json() -> None:
    frame = b"Content-Length: 3\r\n\r\nnop"
    with pytest.raises(protocol.RpcError) as excinfo:
        protocol.read_message(io.BytesIO(frame))
    assert excinfo.value.code == protocol.PARSE_ERROR
    # The body WAS consumed, so the session can keep serving: not fatal.
    assert excinfo.value.fatal is False


def test_read_message_rejects_a_non_object_body() -> None:
    frame = b"Content-Length: 2\r\n\r\n[]"
    with pytest.raises(protocol.RpcError) as excinfo:
        protocol.read_message(io.BytesIO(frame))
    assert excinfo.value.code == protocol.INVALID_REQUEST


def test_error_response_shape() -> None:
    assert protocol.error_response(3, protocol.METHOD_NOT_FOUND, "nope") == {
        "jsonrpc": "2.0",
        "id": 3,
        "error": {"code": -32601, "message": "nope"},
    }


def test_notification_omits_params_when_none() -> None:
    assert protocol.notification("$/logTrace") == {
        "jsonrpc": "2.0",
        "method": "$/logTrace",
    }
