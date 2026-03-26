"""Tests for AsyncJiraCloudDocumentReader attachment fetching."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.jira.async_jira_cloud_reader import AsyncJiraCloudDocumentReader

pytestmark = pytest.mark.connectors


def _make_reader(**kwargs):
    defaults = {
        "base_url": "https://acme.atlassian.net",
        "query": "project = TEST",
        "email": "user@acme.com",
        "api_token": "tok",
        "batch_size": 100,
    }
    defaults.update(kwargs)
    return AsyncJiraCloudDocumentReader(**defaults)


def _fake_search_response(issues):
    """Build a fake JQL search response."""
    resp = MagicMock()
    resp.json.return_value = {"issues": issues, "total": len(issues)}
    resp.raise_for_status = MagicMock()
    return resp


def test_fields_include_attachment_when_enabled():
    reader = _make_reader(include_attachments=True)
    assert "attachment" in reader.fields

    reader2 = _make_reader(include_attachments=False)
    assert "attachment" not in reader2.fields


def test_read_all_documents_without_attachments():
    """Without attachments, returns issues directly."""
    reader = _make_reader(include_attachments=False)

    issues = [{"key": "T-1", "fields": {"updated": "2024-01-01"}}]

    with patch.object(reader, "_read_all_async", new_callable=AsyncMock) as mock_read:
        mock_read.return_value = issues
        result = reader.read_all_documents()

    assert result == issues


def test_enrich_with_attachments_downloads():
    """Test that _enrich_with_attachments downloads attachment bytes."""
    reader = _make_reader(include_attachments=True, max_attachment_size_mb=10)

    issues = [
        {
            "key": "T-1",
            "fields": {
                "attachment": [
                    {
                        "filename": "report.pdf",
                        "content": "https://acme.atlassian.net/att/1",
                        "mimeType": "application/pdf",
                        "size": 1024,
                    },
                ]
            },
        }
    ]

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.content = b"pdf bytes"
        resp.raise_for_status = MagicMock()
        return resp

    with patch(
        "connectors.jira.async_jira_cloud_reader.httpx.AsyncClient"
    ) as MockClient:
        mock_client = AsyncMock()
        mock_client.get = fake_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = asyncio.run(reader._enrich_with_attachments(issues))

    assert len(result) == 1
    assert len(result[0]["attachments"]) == 1
    assert result[0]["attachments"][0]["filename"] == "report.pdf"
    assert result[0]["attachments"][0]["bytes"] == b"pdf bytes"


def test_enrich_skips_oversized_attachments():
    """Attachments exceeding size limit are skipped."""
    reader = _make_reader(include_attachments=True, max_attachment_size_mb=1)

    issues = [
        {
            "key": "T-2",
            "fields": {
                "attachment": [
                    {
                        "filename": "huge.zip",
                        "content": "https://acme.atlassian.net/att/2",
                        "size": 50_000_000,  # 50MB
                    },
                ]
            },
        }
    ]

    with patch(
        "connectors.jira.async_jira_cloud_reader.httpx.AsyncClient"
    ) as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = asyncio.run(reader._enrich_with_attachments(issues))

    assert result[0]["attachments"] == []


def test_fetch_attachment_bytes_failure_returns_none():
    """Failed download returns None."""
    reader = _make_reader(include_attachments=True)

    async def run():
        sem = asyncio.Semaphore(10)
        async with AsyncMock() as client:
            client.get = AsyncMock(side_effect=ConnectionError("fail"))
            result = await reader._fetch_attachment_bytes(client, sem, "https://bad")
            assert result is None

    asyncio.run(run())
