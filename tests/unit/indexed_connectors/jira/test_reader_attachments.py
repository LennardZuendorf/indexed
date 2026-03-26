"""Tests for Jira reader attachment fetching."""

import pytest
from unittest.mock import MagicMock, patch

from connectors.jira.unified_jira_document_reader import (
    UnifiedJiraDocumentReader,
    JiraAuthType,
)

pytestmark = pytest.mark.connectors


class FakeJiraWithAttachments:
    """Fake Jira client that returns issues with attachment metadata."""

    def __init__(self, url=None, username=None, password=None, cloud=None, **kwargs):
        self._issues = [
            {
                "key": "ATT-1",
                "fields": {
                    "updated": "2024-01-01T00:00:00.000+0000",
                    "attachment": [
                        {
                            "filename": "doc.pdf",
                            "content": "https://jira.example.com/attachment/1/doc.pdf",
                            "mimeType": "application/pdf",
                            "size": 1024,
                        },
                        {
                            "filename": "huge.zip",
                            "content": "https://jira.example.com/attachment/2/huge.zip",
                            "mimeType": "application/zip",
                            "size": 999_999_999,  # ~950 MB, over limit
                        },
                    ],
                },
            },
        ]

    def jql(self, jql, fields=None, start=0, limit=50, **kwargs):
        batch = self._issues[start : start + limit]
        return {"issues": batch, "total": len(self._issues)}


class FakeJiraNoAttachments:
    def __init__(self, **kwargs):
        self._issues = [
            {"key": "NO-1", "fields": {"updated": "2024-01-01T00:00:00.000+0000"}},
        ]

    def jql(self, jql, fields=None, start=0, limit=50, **kwargs):
        return {
            "issues": self._issues[start : start + limit],
            "total": len(self._issues),
        }


def test_reader_with_attachments_downloads_bytes(monkeypatch):
    """Test that reader downloads attachment bytes when include_attachments=True."""
    import connectors.jira.unified_jira_document_reader as mod

    monkeypatch.setattr(mod, "Jira", FakeJiraWithAttachments, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://jira.example.com",
        query="project = TEST",
        auth_type=JiraAuthType.SERVER_TOKEN,
        token="test-token",
        include_attachments=True,
        max_attachment_size_mb=10,
    )

    # Mock the HTTP download inside _fetch_attachment_bytes
    mock_response = MagicMock()
    mock_response.content = b"fake pdf content"
    mock_response.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_response):
        docs = list(reader.read_all_documents())

    assert len(docs) == 1
    issue = docs[0]
    assert "attachments" in issue
    # Only doc.pdf should be downloaded (huge.zip exceeds 10MB limit)
    assert len(issue["attachments"]) == 1
    assert issue["attachments"][0]["filename"] == "doc.pdf"
    assert issue["attachments"][0]["bytes"] == b"fake pdf content"


def test_reader_without_attachments_skips_download(monkeypatch):
    """Test that reader does NOT download when include_attachments=False."""
    import connectors.jira.unified_jira_document_reader as mod

    monkeypatch.setattr(mod, "Jira", FakeJiraNoAttachments, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://jira.example.com",
        query="project = TEST",
        auth_type=JiraAuthType.SERVER_TOKEN,
        token="test-token",
        include_attachments=False,
    )

    docs = list(reader.read_all_documents())
    assert len(docs) == 1
    assert "attachments" not in docs[0]


def test_reader_fields_include_attachment_when_enabled(monkeypatch):
    """Fields string includes 'attachment' when include_attachments=True."""
    import connectors.jira.unified_jira_document_reader as mod

    monkeypatch.setattr(mod, "Jira", FakeJiraNoAttachments, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://jira.example.com",
        query="project = TEST",
        auth_type=JiraAuthType.SERVER_TOKEN,
        token="test-token",
        include_attachments=True,
    )
    assert "attachment" in reader.fields

    reader2 = UnifiedJiraDocumentReader(
        base_url="https://jira.example.com",
        query="project = TEST",
        auth_type=JiraAuthType.SERVER_TOKEN,
        token="test-token",
        include_attachments=False,
    )
    assert "attachment" not in reader2.fields


def test_fetch_attachment_bytes_failure_returns_none(monkeypatch):
    """Failed download returns None instead of crashing."""
    import connectors.jira.unified_jira_document_reader as mod

    monkeypatch.setattr(mod, "Jira", FakeJiraWithAttachments, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://jira.example.com",
        query="project = TEST",
        auth_type=JiraAuthType.SERVER_TOKEN,
        token="test-token",
        include_attachments=True,
    )

    with patch("requests.get", side_effect=ConnectionError("network error")):
        docs = list(reader.read_all_documents())

    # Should still return the issue, just with empty attachments
    assert len(docs) == 1
    assert docs[0]["attachments"] == []


def test_fetch_attachment_bytes_with_cloud_auth(monkeypatch):
    """Cloud reader uses email+api_token auth for downloads."""
    import connectors.jira.unified_jira_document_reader as mod

    monkeypatch.setattr(mod, "Jira", FakeJiraWithAttachments, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://acme.atlassian.net",
        query="project = TEST",
        auth_type=JiraAuthType.CLOUD,
        email="user@acme.com",
        api_token="cloud-token",
        include_attachments=True,
    )

    mock_response = MagicMock()
    mock_response.content = b"cloud attachment"
    mock_response.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_response) as mock_get:
        docs = list(reader.read_all_documents())

    assert len(docs[0]["attachments"]) == 1
    # Verify auth was passed
    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs["auth"] == ("user@acme.com", "cloud-token")


def test_fetch_attachment_bytes_with_basic_auth(monkeypatch):
    """Server reader with login/password uses basic auth for downloads."""
    import connectors.jira.unified_jira_document_reader as mod

    monkeypatch.setattr(mod, "Jira", FakeJiraWithAttachments, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://jira.example.com",
        query="project = TEST",
        auth_type=JiraAuthType.SERVER_CREDENTIALS,
        login="admin",
        password="secret",
        include_attachments=True,
    )

    mock_response = MagicMock()
    mock_response.content = b"basic auth attachment"
    mock_response.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_response) as mock_get:
        docs = list(reader.read_all_documents())

    assert len(docs[0]["attachments"]) == 1
    call_kwargs = mock_get.call_args
    assert call_kwargs.kwargs["auth"] == ("admin", "secret")
