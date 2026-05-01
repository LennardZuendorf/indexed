"""Tests for Outline attachment downloading — size cap, inline image extraction, retry."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest


@pytest.fixture
def reader():
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    return OutlineDocumentReader(
        base_url="https://app.getoutline.com",
        api_token="ol_api_test",
        collection_ids=["col1"],
        include_attachments=True,
        download_inline_images=True,
        max_attachment_size_mb=1,
    )


def _make_httpx_response(status: int, content: bytes = b"", headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        content=content,
        headers=headers or {},
    )


# ---------------------------------------------------------------------------
# Inline image URL extraction
# ---------------------------------------------------------------------------

def test_inline_image_regex_extracts_url() -> None:
    from connectors.outline.outline_document_reader import _INLINE_IMAGE_RE

    md = "![screenshot](https://app.getoutline.com/api/attachments.redirect?id=abc-123) some text"
    matches = _INLINE_IMAGE_RE.findall(md)
    assert len(matches) == 1
    assert "id=abc-123" in matches[0]


def test_inline_image_regex_no_match_for_external() -> None:
    from connectors.outline.outline_document_reader import _INLINE_IMAGE_RE

    md = "![logo](https://example.com/logo.png)"
    assert _INLINE_IMAGE_RE.findall(md) == []


def test_inline_image_regex_multiple_matches() -> None:
    from connectors.outline.outline_document_reader import _INLINE_IMAGE_RE

    md = (
        "![a](https://app.getoutline.com/api/attachments.redirect?id=id1)\n"
        "![b](https://app.getoutline.com/api/attachments.redirect?id=id2)"
    )
    matches = _INLINE_IMAGE_RE.findall(md)
    assert len(matches) == 2


# ---------------------------------------------------------------------------
# Size cap
# ---------------------------------------------------------------------------

def test_oversized_attachment_skipped(reader) -> None:
    limit = reader.max_attachment_size_bytes
    oversized = b"x" * (limit + 1)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-length": str(len(oversized)), "content-type": "image/png"}
    mock_resp.content = oversized
    mock_resp.raise_for_status = MagicMock()

    async def run():
        async def mock_get(url, **kwargs):
            return mock_resp

        semaphore = asyncio.Semaphore(10)
        client = AsyncMock()
        client.get = mock_get
        return await reader._download_attachment_url(client, semaphore, "https://example.com/big.png", "big.png", "id1")

    result = asyncio.run(run())
    assert result is None


def test_small_attachment_downloaded(reader) -> None:
    data = b"fake image bytes"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-length": str(len(data)), "content-type": "image/png"}
    mock_resp.content = data
    mock_resp.raise_for_status = MagicMock()

    async def run():
        async def mock_get(url, **kwargs):
            return mock_resp

        semaphore = asyncio.Semaphore(10)
        client = AsyncMock()
        client.get = mock_get
        return await reader._download_attachment_url(client, semaphore, "https://example.com/img.png", "img.png", "id2")

    result = asyncio.run(run())
    assert result is not None
    assert result["bytes"] == data
    assert result["filename"] == "img.png"
    assert result["id"] == "id2"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_failed_download_returns_none(reader) -> None:
    async def run():
        async def mock_get(url, **kwargs):
            raise httpx.ConnectError("connection refused")

        semaphore = asyncio.Semaphore(10)
        client = AsyncMock()
        client.get = mock_get
        return await reader._download_attachment_url(client, semaphore, "https://bad.host/img.png", "img.png", "id3")

    result = asyncio.run(run())
    assert result is None


def test_list_attachments_failure_returns_empty(reader) -> None:
    async def run():
        async def mock_post(*args, **kwargs):
            raise httpx.ConnectError("connection refused")

        semaphore = asyncio.Semaphore(10)
        client = AsyncMock()
        client.post = mock_post
        return await reader._list_attachments(client, semaphore, "doc-id-1")

    result = asyncio.run(run())
    assert result == []
