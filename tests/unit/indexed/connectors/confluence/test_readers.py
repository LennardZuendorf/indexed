"""Tests for the AsyncConfluenceCloudDocumentReader page-listing pipeline."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError

from indexed.connectors.confluence.async_confluence_cloud_reader import (
    AsyncConfluenceCloudDocumentReader,
)

pytestmark = pytest.mark.connectors


def _success_response(
    items: list[dict[str, Any]], total: int, next_cursor: str | None = None
) -> MagicMock:
    resp = MagicMock()
    payload: dict[str, Any] = {"results": items, "totalSize": total}
    if next_cursor:
        payload["_links"] = {
            "next": f"/wiki/rest/api/search?cursor={next_cursor}&limit=1"
        }
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _error_response(status_code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason = "Service Unavailable"
    resp.url = "https://company.atlassian.net/wiki/rest/api/search"
    resp.text = "Service Unavailable"
    resp.json.return_value = {"message": "Service Unavailable"}
    resp.raise_for_status.side_effect = HTTPError(response=resp)
    return resp


@pytest.fixture
def async_reader() -> AsyncConfluenceCloudDocumentReader:
    return AsyncConfluenceCloudDocumentReader(
        base_url="https://company.atlassian.net",
        query="space = DEV",
        email="user@example.com",
        api_token="tok",
        batch_size=2,
        number_of_retries=2,
        max_skipped_items_in_row=3,
    )


def test_read_pages_sync_pagination(async_reader):
    """Reads all pages across multiple offset-based batches."""
    items = [{"id": str(i)} for i in range(5)]
    responses = [
        _success_response(items[:2], total=5),
        _success_response(items[2:4], total=5),
        _success_response(items[4:], total=5),
    ]

    with patch("requests.get", side_effect=responses) as mock_get:
        result = list(async_reader._read_pages_sync())

    assert [item["id"] for item in result] == ["0", "1", "2", "3", "4"]
    assert mock_get.call_count == 3


def test_read_pages_sync_skip_and_continue_on_persistent_page_failure(
    monkeypatch,
):
    """R13: a page that returns a transient 5xx is retried (via
    execute_with_retry, which the raw ``requests.get`` call previously had
    NO retry wrapping at all) and, once retries are exhausted, skipped and
    logged rather than aborting the whole read with zero docs. Reading
    continues past the skipped page using Confluence's real ``totalSize``.

    Pre-fix, ``_read_pages_sync`` calls raw ``requests.get`` with no retry
    and no skip-and-continue: a single failing page raises immediately and
    the generator yields nothing at all past that point.
    """
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)

    reader = AsyncConfluenceCloudDocumentReader(
        base_url="https://company.atlassian.net",
        query="space = DEV",
        email="user@example.com",
        api_token="tok",
        batch_size=2,
        number_of_retries=2,
        max_skipped_items_in_row=3,
    )

    responses = [
        _success_response([{"id": "P1"}, {"id": "P2"}], total=5),  # start=0
        _error_response(503),  # start=2, batch=2, attempt 1
        _error_response(503),  # start=2, batch=2, attempt 2 (exhausted)
        _error_response(503),  # start=2, batch=1, attempt 1
        _error_response(503),  # start=2, batch=1, attempt 2 (exhausted -> skip)
        _success_response([{"id": "P4"}], total=5),  # start=3, batch=1
        _success_response([{"id": "P5"}], total=5),  # start=4, batch=2
    ]

    with patch("requests.get", side_effect=responses) as mock_get:
        result = list(reader._read_pages_sync())

    assert [item["id"] for item in result] == ["P1", "P2", "P4", "P5"]
    assert mock_get.call_count == 7


def test_read_pages_sync_retries_transient_failure_then_succeeds(monkeypatch):
    """R13 parity: the page fetch is now wrapped in ``execute_with_retry``
    (previously a raw, unretried ``requests.get`` call). A single transient
    5xx on a page recovers via retry with no skip needed at all — matching
    the sync sibling's (``ConfluenceDocumentReader``) retry behavior.

    Pre-fix, the first 503 raises immediately with no retry attempted.
    """
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)

    reader = AsyncConfluenceCloudDocumentReader(
        base_url="https://company.atlassian.net",
        query="space = DEV",
        email="user@example.com",
        api_token="tok",
        batch_size=2,
        number_of_retries=2,
    )

    responses = [
        _success_response([{"id": "P1"}, {"id": "P2"}], total=5),  # start=0
        _error_response(503),  # start=2, attempt 1 (transient)
        _success_response([{"id": "P3"}, {"id": "P4"}], total=5),  # start=2, attempt 2
        _success_response([{"id": "P5"}], total=5),  # start=4
    ]

    with patch("requests.get", side_effect=responses) as mock_get:
        result = list(reader._read_pages_sync())

    assert [item["id"] for item in result] == ["P1", "P2", "P3", "P4", "P5"]
    assert mock_get.call_count == 4
