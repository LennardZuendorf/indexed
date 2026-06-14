"""End-to-end mocked integration tests for AsyncJiraCloudDocumentReader.

Exercises read_all_documents() with requests.post mocked so the full sequence
approximate-count (optional) → search/jql pagination runs through real code.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from connectors.jira.async_jira_cloud_reader import AsyncJiraCloudDocumentReader

pytestmark = pytest.mark.integration


def _search_resp(
    issues: list[dict[str, Any]], next_token: str | None = None
) -> MagicMock:
    payload: dict[str, Any] = {"issues": issues}
    if next_token:
        payload["nextPageToken"] = next_token
    resp = MagicMock()
    resp.json.return_value = payload
    resp.ok = True
    resp.status_code = 200
    resp.url = "https://acme.atlassian.net/rest/api/3/search/jql"
    resp.text = ""
    return resp


def _count_resp(count: int) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"count": count}
    resp.ok = True
    resp.status_code = 200
    resp.url = "https://acme.atlassian.net/rest/api/3/search/approximate-count"
    resp.text = ""
    return resp


def _make_reader(**kwargs: object) -> AsyncJiraCloudDocumentReader:
    defaults: dict[str, object] = {
        "base_url": "https://acme.atlassian.net",
        "query": "project = TEST",
        "email": "user@acme.com",
        "api_token": "tok",
        "batch_size": 2,
        "include_attachments": False,
    }
    defaults.update(kwargs)
    return AsyncJiraCloudDocumentReader(**defaults)


def test_read_all_documents_integration_multi_page() -> None:
    """read_all_documents orchestrates sequential search/jql pages."""
    reader = _make_reader()
    issues = [{"key": f"T-{i}", "fields": {"updated": "2024-01-01"}} for i in range(3)]
    responses = [
        _search_resp(issues[:2], next_token="2"),
        _search_resp(issues[2:]),
    ]

    with patch("requests.post", side_effect=responses) as mock_post:
        result = reader.read_all_documents()

    assert len(result) == 3
    assert result[0]["key"] == "T-0"
    assert mock_post.call_count == 2
    first_body = mock_post.call_args_list[0].kwargs["json"]
    assert first_body["jql"] == "project = TEST"
    assert "nextPageToken" not in first_body
    second_body = mock_post.call_args_list[1].kwargs["json"]
    assert second_body["nextPageToken"] == "2"


def test_get_number_of_documents_integration() -> None:
    """get_number_of_documents hits approximate-count endpoint."""
    reader = _make_reader()

    with patch("requests.post", return_value=_count_resp(17)) as mock_post:
        count = reader.get_number_of_documents()

    assert count == 17
    assert mock_post.call_count == 1
    assert "approximate-count" in mock_post.call_args.args[0]
    assert mock_post.call_args.kwargs["json"] == {"jql": "project = TEST"}


def test_read_all_documents_empty_result() -> None:
    """Zero issues returns empty list without follow-up pages."""
    reader = _make_reader()

    with patch("requests.post", return_value=_search_resp([])) as mock_post:
        result = reader.read_all_documents()

    assert result == []
    assert mock_post.call_count == 1


def test_search_api_error_surfaces_jira_cloud_api_error() -> None:
    """Removed-endpoint style errors raise JiraCloudAPIError."""
    from connectors.jira.async_jira_cloud_reader import JiraCloudAPIError

    reader = _make_reader()
    resp = MagicMock()
    resp.ok = False
    resp.status_code = 410
    resp.url = "https://acme.atlassian.net/rest/api/3/search"
    resp.text = ""
    resp.json.return_value = {
        "errorMessages": [
            "The requested API has been removed. "
            "Please migrate to the /rest/api/3/search/jql API."
        ],
        "errors": {},
    }

    with patch("requests.post", return_value=resp):
        with pytest.raises(JiraCloudAPIError, match="removed"):
            reader.read_all_documents()
