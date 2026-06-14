"""Tests for Jira document readers."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from connectors.jira.async_jira_cloud_reader import AsyncJiraCloudDocumentReader
from connectors.jira.unified_jira_document_reader import (
    UnifiedJiraDocumentReader,
    JiraAuthType,
)

pytestmark = pytest.mark.connectors  # Mark all tests in this file as connector tests


class FakeJiraCloud:
    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        cloud: bool | None = None,
        **kwargs: Any,
    ) -> None:
        self._issues = [
            {"key": "ISSUE-1", "fields": {"updated": "2024-01-01T00:00:00.000+0000"}},
            {"key": "ISSUE-2", "fields": {"updated": "2024-01-02T00:00:00.000+0000"}},
            {"key": "ISSUE-3", "fields": {"updated": "2024-01-03T00:00:00.000+0000"}},
        ]

    def approximate_issue_count(self, jql: str) -> dict[str, Any]:
        return {"count": len(self._issues)}

    def enhanced_jql(
        self,
        jql: str,
        fields: str | list[str] | None = None,
        nextPageToken: str | None = None,
        limit: int = 50,
        expand: str | list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        start = int(nextPageToken) if nextPageToken else 0
        batch = self._issues[start : start + limit] if limit else self._issues[start:]
        result: dict[str, Any] = {"issues": batch}
        next_start = start + len(batch)
        if next_start < len(self._issues):
            result["nextPageToken"] = str(next_start)
        return result


class FakeJiraServer:
    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        cloud: bool | None = None,
        **kwargs: Any,
    ) -> None:
        self._issues = [
            {"key": "S-1", "fields": {"updated": "2024-02-01T00:00:00.000+0000"}},
            {"key": "S-2", "fields": {"updated": "2024-02-02T00:00:00.000+0000"}},
        ]

    def jql(
        self,
        jql: str,
        fields: str | list[str] | None = None,
        start: int = 0,
        limit: int = 50,
        expand: str | list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        batch = self._issues[start : start + limit] if limit else self._issues[start:]
        return {
            "issues": batch,
            "total": len(self._issues),
            "startAt": start,
            "maxResults": limit,
        }


def _make_search_response(
    issues: list[dict[str, Any]], next_token: str | None = None
) -> MagicMock:
    resp = MagicMock()
    payload: dict[str, Any] = {"issues": issues}
    if next_token:
        payload["nextPageToken"] = next_token
    resp.json.return_value = payload
    resp.ok = True
    resp.status_code = 200
    resp.url = "https://acme.atlassian.net/rest/api/3/search/jql"
    resp.text = ""
    return resp


def _make_count_response(count: int) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"count": count}
    resp.ok = True
    resp.status_code = 200
    resp.url = "https://acme.atlassian.net/rest/api/3/search/approximate-count"
    resp.text = ""
    return resp


@pytest.fixture
def async_reader() -> AsyncJiraCloudDocumentReader:
    return AsyncJiraCloudDocumentReader(
        base_url="https://acme.atlassian.net",
        query="project = TEST",
        email="user@acme.com",
        api_token="tok",
        batch_size=2,
    )


def test_cloud_reader_count_and_pagination(monkeypatch):
    """Test cloud reader document counting and pagination."""
    import connectors.jira.unified_jira_document_reader as unified_mod

    monkeypatch.setattr(unified_mod, "Jira", FakeJiraCloud, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://acme.atlassian.net",
        query="project = TEST",
        auth_type=JiraAuthType.CLOUD,
        email="x@acme.com",
        api_token="token",
        batch_size=2,
    )

    assert reader.get_number_of_documents() == 3

    docs = list(reader.read_all_documents())
    assert len(docs) == 3
    assert docs[0]["key"] == "ISSUE-1"
    assert docs[-1]["key"] == "ISSUE-3"


def test_server_reader_count_and_pagination(monkeypatch):
    """Test server reader document counting and pagination."""
    import connectors.jira.unified_jira_document_reader as unified_mod

    monkeypatch.setattr(unified_mod, "Jira", FakeJiraServer, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://jira.example.com",
        query="project = APP",
        auth_type=JiraAuthType.SERVER_TOKEN,
        token="pat-token",
        batch_size=1,
    )

    assert reader.get_number_of_documents() == 2

    docs = list(reader.read_all_documents())
    assert len(docs) == 2
    assert docs[0]["key"] == "S-1"


def test_pagination_terminates_at_next_page_token(async_reader):
    """Async reader fetches all pages until nextPageToken is absent."""
    issues = [{"key": f"I-{i}", "fields": {"updated": "2024-01-01"}} for i in range(5)]
    responses = [
        _make_search_response(issues[:2], next_token="2"),
        _make_search_response(issues[2:4], next_token="4"),
        _make_search_response(issues[4:]),
    ]

    with patch("requests.post", side_effect=responses) as mock_post:
        result = async_reader._read_issues_sync()

    assert len(result) == 5
    assert mock_post.call_count == 3
    assert all(
        call.kwargs["json"]["jql"] == "project = TEST"
        for call in mock_post.call_args_list
    )


def test_pagination_with_exact_page_boundary(async_reader):
    """Async reader stops cleanly when last page fills the batch exactly."""
    issues = [{"key": f"I-{i}", "fields": {"updated": "2024-01-01"}} for i in range(4)]
    responses = [
        _make_search_response(issues[:2], next_token="2"),
        _make_search_response(issues[2:]),
    ]

    with patch("requests.post", side_effect=responses) as mock_post:
        result = async_reader._read_issues_sync()

    assert len(result) == 4
    assert mock_post.call_count == 2


def test_async_reader_approximate_count(async_reader):
    """get_number_of_documents uses approximate-count endpoint."""
    with patch(
        "requests.post",
        return_value=_make_count_response(42),
    ) as mock_post:
        count = async_reader.get_number_of_documents()

    assert count == 42
    assert "approximate-count" in mock_post.call_args.args[0]


def test_reader_validation_cloud_requires_email_and_token():
    """Test cloud auth validation."""
    with pytest.raises(
        ValueError, match="Cloud authentication requires both 'email' and 'api_token'"
    ):
        UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",
            query="project = TEST",
            auth_type=JiraAuthType.CLOUD,
        )


def test_reader_validation_server_token_requires_token():
    """Test server token auth validation."""
    with pytest.raises(ValueError, match="Token authentication requires 'token'"):
        UnifiedJiraDocumentReader(
            base_url="https://jira.example.com",
            query="project = TEST",
            auth_type=JiraAuthType.SERVER_TOKEN,
        )


def test_reader_validation_server_creds_requires_login_password():
    """Test server credentials auth validation."""
    with pytest.raises(
        ValueError,
        match="Credential authentication requires both 'login' and 'password'",
    ):
        UnifiedJiraDocumentReader(
            base_url="https://jira.example.com",
            query="project = TEST",
            auth_type=JiraAuthType.SERVER_CREDENTIALS,
        )


def test_reader_url_validation_cloud():
    """Test cloud URL validation."""
    with pytest.raises(ValueError, match="Cloud URLs must end with .atlassian.net"):
        UnifiedJiraDocumentReader(
            base_url="https://jira.example.com",
            query="project = TEST",
            auth_type=JiraAuthType.CLOUD,
            email="x@acme.com",
            api_token="token",
        )


def test_reader_url_validation_server():
    """Test server URL validation."""
    with pytest.raises(
        ValueError, match="Server/DC URLs should not end with .atlassian.net"
    ):
        UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",
            query="project = TEST",
            auth_type=JiraAuthType.SERVER_TOKEN,
            token="token",
        )


def test_reader_details(monkeypatch):
    """Test get_reader_details returns correct information."""
    import connectors.jira.unified_jira_document_reader as unified_mod

    monkeypatch.setattr(unified_mod, "Jira", FakeJiraCloud, raising=True)

    reader = UnifiedJiraDocumentReader(
        base_url="https://acme.atlassian.net",
        query="project = TEST",
        auth_type=JiraAuthType.CLOUD,
        email="x@acme.com",
        api_token="token",
        batch_size=100,
    )

    details = reader.get_reader_details()

    assert details["type"] == "jiraCloud"
    assert details["baseUrl"] == "https://acme.atlassian.net"
    assert details["query"] == "project = TEST"
    assert details["batchSize"] == 100
