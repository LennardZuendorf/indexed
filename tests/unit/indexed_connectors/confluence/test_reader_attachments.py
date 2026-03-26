"""Tests for Confluence reader attachment fetching."""

import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from connectors.confluence.confluence_document_reader import ConfluenceDocumentReader
from connectors.confluence.async_confluence_cloud_reader import (
    AsyncConfluenceCloudDocumentReader,
)

pytestmark = pytest.mark.connectors


# ---------------------------------------------------------------------------
# Confluence Server/DC reader
# ---------------------------------------------------------------------------


class TestConfluenceDocumentReaderAttachments:
    """Test attachment fetching in ConfluenceDocumentReader."""

    def _make_reader(self, include_attachments=True, max_mb=10):
        return ConfluenceDocumentReader(
            base_url="https://confluence.example.com",
            query="space = DEV",
            token="test-token",
            include_attachments=include_attachments,
            max_attachment_size_mb=max_mb,
        )

    def test_read_all_documents_includes_attachments(self):
        """When include_attachments=True, doc dict has 'attachments' key."""
        reader = self._make_reader(include_attachments=True)

        page = {
            "id": "123",
            "title": "Test",
            "children": {"comment": {"size": 0}},
        }

        att_api_response = {
            "results": [
                {
                    "title": "doc.pdf",
                    "extensions": {"fileSize": 1024},
                    "_links": {"download": "/download/attachments/123/doc.pdf"},
                    "metadata": {"mediaType": "application/pdf"},
                },
            ],
            "size": 1,
        }

        # Mock __read_items to yield one page
        with (
            patch.object(
                reader, "_ConfluenceDocumentReader__read_items", return_value=[page]
            ),
            patch.object(
                reader, "_ConfluenceDocumentReader__read_comments", return_value=[]
            ),
            patch.object(
                reader,
                "_ConfluenceDocumentReader__request",
                return_value=att_api_response,
            ),
            patch.object(
                reader,
                "_ConfluenceDocumentReader__fetch_attachment_bytes",
                return_value=b"pdf content",
            ),
        ):
            docs = list(reader.read_all_documents())

        assert len(docs) == 1
        assert "attachments" in docs[0]
        assert len(docs[0]["attachments"]) == 1
        assert docs[0]["attachments"][0]["filename"] == "doc.pdf"
        assert docs[0]["attachments"][0]["bytes"] == b"pdf content"

    def test_read_all_documents_no_attachments_when_disabled(self):
        """When include_attachments=False, doc dict has no 'attachments' key."""
        reader = self._make_reader(include_attachments=False)

        page = {
            "id": "123",
            "title": "Test",
            "children": {"comment": {"size": 0}},
        }

        with (
            patch.object(
                reader, "_ConfluenceDocumentReader__read_items", return_value=[page]
            ),
            patch.object(
                reader, "_ConfluenceDocumentReader__read_comments", return_value=[]
            ),
        ):
            docs = list(reader.read_all_documents())

        assert len(docs) == 1
        assert "attachments" not in docs[0]

    def test_oversized_attachments_skipped(self):
        """Attachments exceeding size limit are skipped."""
        reader = self._make_reader(include_attachments=True, max_mb=1)

        page = {"id": "123", "title": "Test", "children": {"comment": {"size": 0}}}

        att_api_response = {
            "results": [
                {
                    "title": "huge.zip",
                    "extensions": {"fileSize": 50_000_000},  # 50MB
                    "_links": {"download": "/download/attachments/123/huge.zip"},
                    "metadata": {},
                },
            ],
            "size": 1,
        }

        with (
            patch.object(
                reader, "_ConfluenceDocumentReader__read_items", return_value=[page]
            ),
            patch.object(
                reader, "_ConfluenceDocumentReader__read_comments", return_value=[]
            ),
            patch.object(
                reader,
                "_ConfluenceDocumentReader__request",
                return_value=att_api_response,
            ),
        ):
            docs = list(reader.read_all_documents())

        assert docs[0]["attachments"] == []

    def test_attachment_no_download_link_skipped(self):
        """Attachments without download link are skipped."""
        reader = self._make_reader(include_attachments=True)

        page = {"id": "123", "title": "Test", "children": {"comment": {"size": 0}}}

        att_api_response = {
            "results": [
                {
                    "title": "no_link.pdf",
                    "extensions": {"fileSize": 100},
                    "_links": {},  # no download
                    "metadata": {},
                },
            ],
            "size": 1,
        }

        with (
            patch.object(
                reader, "_ConfluenceDocumentReader__read_items", return_value=[page]
            ),
            patch.object(
                reader, "_ConfluenceDocumentReader__read_comments", return_value=[]
            ),
            patch.object(
                reader,
                "_ConfluenceDocumentReader__request",
                return_value=att_api_response,
            ),
        ):
            docs = list(reader.read_all_documents())

        assert docs[0]["attachments"] == []

    def test_attachment_download_failure_skipped(self):
        """Failed attachment download is skipped gracefully."""
        reader = self._make_reader(include_attachments=True)

        page = {"id": "123", "title": "Test", "children": {"comment": {"size": 0}}}

        att_api_response = {
            "results": [
                {
                    "title": "fail.pdf",
                    "extensions": {"fileSize": 100},
                    "_links": {"download": "/download/fail.pdf"},
                    "metadata": {},
                },
            ],
            "size": 1,
        }

        with (
            patch.object(
                reader, "_ConfluenceDocumentReader__read_items", return_value=[page]
            ),
            patch.object(
                reader, "_ConfluenceDocumentReader__read_comments", return_value=[]
            ),
            patch.object(
                reader,
                "_ConfluenceDocumentReader__request",
                return_value=att_api_response,
            ),
            patch.object(
                reader,
                "_ConfluenceDocumentReader__fetch_attachment_bytes",
                return_value=None,
            ),
        ):
            docs = list(reader.read_all_documents())

        assert docs[0]["attachments"] == []

    def test_fetch_attachment_bytes_success(self):
        """Test successful attachment byte download."""
        reader = self._make_reader()

        mock_resp = MagicMock()
        mock_resp.content = b"file bytes"
        mock_resp.raise_for_status = MagicMock()

        with patch(
            "connectors.confluence.confluence_document_reader.requests.get",
            return_value=mock_resp,
        ):
            result = reader._ConfluenceDocumentReader__fetch_attachment_bytes(
                "https://confluence.example.com/download/test.pdf"
            )

        assert result == b"file bytes"

    def test_fetch_attachment_bytes_failure(self):
        """Test failed download returns None."""
        reader = self._make_reader()

        with patch(
            "connectors.confluence.confluence_document_reader.requests.get",
            side_effect=ConnectionError("fail"),
        ):
            result = reader._ConfluenceDocumentReader__fetch_attachment_bytes(
                "https://confluence.example.com/download/fail.pdf"
            )

        assert result is None


# ---------------------------------------------------------------------------
# Confluence Cloud async reader
# ---------------------------------------------------------------------------


class TestAsyncConfluenceCloudReaderAttachments:
    """Test attachment fetching in AsyncConfluenceCloudDocumentReader."""

    def _make_reader(self, include_attachments=True, max_mb=10):
        return AsyncConfluenceCloudDocumentReader(
            base_url="https://company.atlassian.net",
            query="space = DEV",
            email="user@example.com",
            api_token="tok",
            include_attachments=include_attachments,
            max_attachment_size_mb=max_mb,
        )

    def test_include_attachments_stored(self):
        reader = self._make_reader(include_attachments=True)
        assert reader.include_attachments is True

        reader2 = self._make_reader(include_attachments=False)
        assert reader2.include_attachments is False

    def test_yield_pages_with_attachments(self):
        """_yield_pages_with_comments includes attachments when enabled."""
        reader = self._make_reader(include_attachments=True)

        pages = [{"content": {"id": "1", "children": {"comment": {"size": 0}}}}]

        with (
            patch.object(
                reader,
                "_fetch_all_comments_async",
                new_callable=AsyncMock,
                return_value={0: []},
            ),
            patch.object(
                reader,
                "_fetch_all_attachments_async",
                new_callable=AsyncMock,
                return_value={0: [{"filename": "test.pdf", "bytes": b"data"}]},
            ),
        ):
            results = list(reader._yield_pages_with_comments(pages))

        assert len(results) == 1
        assert "attachments" in results[0]
        assert results[0]["attachments"][0]["filename"] == "test.pdf"

    def test_yield_pages_without_attachments(self):
        """No attachments key when include_attachments=False."""
        reader = self._make_reader(include_attachments=False)

        pages = [{"content": {"id": "1", "children": {"comment": {"size": 0}}}}]

        with patch.object(
            reader,
            "_fetch_all_comments_async",
            new_callable=AsyncMock,
            return_value={0: []},
        ):
            results = list(reader._yield_pages_with_comments(pages))

        assert "attachments" not in results[0]

    def test_fetch_attachments_for_page_no_content_id(self):
        """Page without content id returns empty list."""
        reader = self._make_reader()

        async def run():
            sem = asyncio.Semaphore(5)
            client = AsyncMock()
            return await reader._fetch_attachments_for_page(client, sem, {})

        result = asyncio.run(run())
        assert result == []

    def test_fetch_attachments_for_page_oversized_skipped(self):
        """Oversized attachments are skipped in async reader."""
        reader = self._make_reader(max_mb=1)

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "results": [
                {
                    "title": "huge.bin",
                    "extensions": {"fileSize": 50_000_000},
                    "_links": {"download": "/download/huge.bin"},
                    "metadata": {},
                },
            ]
        }
        list_resp.raise_for_status = MagicMock()

        async def run():
            sem = asyncio.Semaphore(5)
            client = AsyncMock()
            client.get = AsyncMock(return_value=list_resp)
            page = {"content": {"id": "99"}}
            return await reader._fetch_attachments_for_page(client, sem, page)

        result = asyncio.run(run())
        assert result == []

    def test_fetch_attachments_for_page_no_download_link(self):
        """Attachments without download link are skipped."""
        reader = self._make_reader()

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "results": [
                {
                    "title": "no_link.pdf",
                    "extensions": {"fileSize": 100},
                    "_links": {},
                    "metadata": {},
                },
            ]
        }
        list_resp.raise_for_status = MagicMock()

        async def run():
            sem = asyncio.Semaphore(5)
            client = AsyncMock()
            client.get = AsyncMock(return_value=list_resp)
            page = {"content": {"id": "99"}}
            return await reader._fetch_attachments_for_page(client, sem, page)

        result = asyncio.run(run())
        assert result == []

    def test_fetch_attachments_for_page_success(self):
        """Successfully downloads attachment bytes."""
        reader = self._make_reader()

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "results": [
                {
                    "title": "good.pdf",
                    "extensions": {"fileSize": 100},
                    "_links": {"download": "/download/good.pdf"},
                    "metadata": {"mediaType": "application/pdf"},
                },
            ]
        }
        list_resp.raise_for_status = MagicMock()

        download_resp = MagicMock()
        download_resp.content = b"pdf data"
        download_resp.raise_for_status = MagicMock()

        async def run():
            sem = asyncio.Semaphore(5)
            client = AsyncMock()

            # First call = list attachments, second call = download
            client.get = AsyncMock(side_effect=[list_resp, download_resp])
            page = {"content": {"id": "99"}}
            return await reader._fetch_attachments_for_page(client, sem, page)

        result = asyncio.run(run())
        assert len(result) == 1
        assert result[0]["filename"] == "good.pdf"
        assert result[0]["bytes"] == b"pdf data"

    def test_fetch_attachments_for_page_download_error(self):
        """Download failure for individual attachment is handled."""
        reader = self._make_reader()

        list_resp = MagicMock()
        list_resp.json.return_value = {
            "results": [
                {
                    "title": "fail.pdf",
                    "extensions": {"fileSize": 100},
                    "_links": {"download": "/download/fail.pdf"},
                    "metadata": {},
                },
            ]
        }
        list_resp.raise_for_status = MagicMock()

        async def run():
            sem = asyncio.Semaphore(5)
            client = AsyncMock()
            # First call succeeds (list), second fails (download)
            client.get = AsyncMock(
                side_effect=[list_resp, ConnectionError("download failed")]
            )
            page = {"content": {"id": "99"}}
            return await reader._fetch_attachments_for_page(client, sem, page)

        result = asyncio.run(run())
        assert result == []

    def test_fetch_attachments_for_page_list_error(self):
        """Error listing attachments returns empty list."""
        reader = self._make_reader()

        async def run():
            sem = asyncio.Semaphore(5)
            client = AsyncMock()
            client.get = AsyncMock(side_effect=ConnectionError("list failed"))
            page = {"content": {"id": "99"}}
            return await reader._fetch_attachments_for_page(client, sem, page)

        result = asyncio.run(run())
        assert result == []

    def test_fetch_all_attachments_async_handles_exceptions(self):
        """Exceptions from individual page fetches are caught."""
        reader = self._make_reader()

        pages = [
            {"content": {"id": "1"}},
            {"content": {"id": "2"}},
        ]

        with patch.object(
            reader,
            "_fetch_attachments_for_page",
            new_callable=AsyncMock,
            side_effect=[
                [{"filename": "ok.pdf", "bytes": b"ok"}],
                RuntimeError("page 2 failed"),
            ],
        ):
            result = asyncio.run(reader._fetch_all_attachments_async(pages))

        assert len(result[0]) == 1
        assert result[1] == []  # failed page gets empty list
