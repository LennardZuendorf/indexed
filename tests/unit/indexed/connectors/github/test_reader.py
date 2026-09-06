import asyncio
from unittest.mock import patch

import pytest

from indexed.connectors.github.github_graphql_reader import (
    GitHubGraphQLError,
    GitHubGraphQLReader,
)
from ._fakes import FakeAsyncClient, FakeResponse


def _issue_node(number: int, title: str) -> dict:
    return {
        "id": f"I_{number}",
        "number": number,
        "title": title,
        "body": f"Body for {title}",
        "state": "OPEN",
        "url": f"https://github.com/octo/hello/issues/{number}",
        "updatedAt": "2026-06-20T10:00:00Z",
        "createdAt": "2026-06-19T10:00:00Z",
        "author": {"login": "octocat"},
        "labels": {"nodes": [{"name": "bug"}]},
        "comments": {
            "nodes": [
                {
                    "author": {"login": "reviewer"},
                    "body": "lgtm",
                    "createdAt": "2026-06-20T11:00:00Z",
                }
            ]
        },
    }


def _issues_page(nodes: list[dict], has_next: bool, end_cursor: str | None) -> dict:
    return {
        "data": {
            "repository": {
                "issues": {
                    "nodes": nodes,
                    "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
                }
            }
        }
    }


def _reader(**overrides) -> GitHubGraphQLReader:
    kwargs = dict(
        graphql_url="https://api.github.com/graphql",
        token="ghp_test",
        repos=[("octo", "hello")],
        project=None,
        state="all",
        labels=None,
        include_pull_requests=False,
        include_comments=True,
        page_size=2,
        max_concurrent_requests=2,
        number_of_retries=3,
        retry_delay=0.0,
    )
    kwargs.update(overrides)
    return GitHubGraphQLReader(**kwargs)


def test_paginates_two_pages():
    pages = [
        _issues_page([_issue_node(1, "First")], has_next=True, end_cursor="cursor-1"),
        _issues_page([_issue_node(2, "Second")], has_next=False, end_cursor=None),
    ]
    calls = []

    def router(body):
        calls.append(body["variables"].get("after"))
        return FakeResponse(200, pages[len(calls) - 1])

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        docs = list(_reader().read_all_documents())

    assert [d["id"] for d in docs] == ["octo/hello#1", "octo/hello#2"]
    assert calls == [None, "cursor-1"]


def test_maps_issue_fields():
    page = _issues_page(
        [_issue_node(7, "Flaky retry logic")], has_next=False, end_cursor=None
    )

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(lambda body: FakeResponse(200, page), **kw),
    ):
        (doc,) = list(_reader().read_all_documents())

    assert doc["url"] == "https://github.com/octo/hello/issues/7"
    assert doc["modifiedTime"] == "2026-06-20T10:00:00Z"
    assert doc["title"] == "Flaky retry logic"
    assert doc["labels"] == ["bug"]
    assert doc["author"] == "octocat"
    assert doc["kind"] == "issue"
    assert doc["comments"] == [{"author": "reviewer", "body": "lgtm"}]


def test_rate_limit_retries_then_succeeds():
    page = _issues_page([_issue_node(1, "First")], has_next=False, end_cursor=None)
    attempts = {"n": 0}

    def router(body):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return FakeResponse(200, {"errors": [{"type": "RATE_LIMITED"}]}, headers={})
        return FakeResponse(200, page)

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        docs = list(_reader().read_all_documents())

    assert attempts["n"] == 3
    assert len(docs) == 1


def test_rate_limit_exhausts_retries_and_raises():
    def router(body):
        return FakeResponse(200, {"errors": [{"type": "RATE_LIMITED"}]}, headers={})

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        with pytest.raises(GitHubGraphQLError):
            list(_reader(number_of_retries=2).read_all_documents())


def test_labels_and_state_filter_passed_as_variables():
    captured = {}

    def router(body):
        captured.update(body["variables"])
        return FakeResponse(200, _issues_page([], has_next=False, end_cursor=None))

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        list(_reader(state="open", labels=["bug"]).read_all_documents())

    assert captured["states"] == ["OPEN"]
    assert captured["labels"] == ["bug"]


def test_get_reader_details_shape():
    details = _reader(labels=["bug"]).get_reader_details()
    assert details["type"] == "github"
    assert details["repos"] == ["octo/hello"]
    assert details["state"] == "all"
    assert details["labels"] == ["bug"]
    assert details["includePullRequests"] is False


def test_concurrency_bounded_by_semaphore():
    """With more repos than max_concurrent_requests, peak in-flight requests
    must never exceed the semaphore's bound — deleting `async with semaphore`
    from `_post_graphql` should make this test fail."""
    repos = [("octo", f"repo{i}") for i in range(6)]
    max_concurrent = 2
    state = {"active": 0, "peak": 0}

    async def router(body):
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        await asyncio.sleep(0.01)
        state["active"] -= 1
        return FakeResponse(200, _issues_page([], has_next=False, end_cursor=None))

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        list(
            _reader(
                repos=repos, max_concurrent_requests=max_concurrent
            ).read_all_documents()
        )

    assert state["peak"] > 1, "expected genuine overlap between requests"
    assert state["peak"] <= max_concurrent


def test_http_429_status_retries_then_succeeds():
    page = _issues_page([_issue_node(1, "First")], has_next=False, end_cursor=None)
    attempts = {"n": 0}

    def router(body):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return FakeResponse(429, {}, headers={})
        return FakeResponse(200, page)

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        docs = list(_reader().read_all_documents())

    assert attempts["n"] == 3
    assert len(docs) == 1


def test_http_403_with_rate_limit_headers_retries_then_succeeds():
    page = _issues_page([_issue_node(1, "First")], has_next=False, end_cursor=None)
    attempts = {"n": 0}

    def router(body):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return FakeResponse(403, {}, headers={"X-RateLimit-Remaining": "0"})
        return FakeResponse(200, page)

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        docs = list(_reader().read_all_documents())

    assert attempts["n"] == 3
    assert len(docs) == 1


def test_http_403_without_rate_limit_headers_raises_immediately():
    """A plain 403 (bad scope, SAML enforcement, repo access denied) must not
    be retried and must not be reported as a rate limit."""
    attempts = {"n": 0}

    def router(body):
        attempts["n"] += 1
        return FakeResponse(403, {}, headers={})

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        with pytest.raises(GitHubGraphQLError) as exc_info:
            list(_reader(number_of_retries=3).read_all_documents())

    assert attempts["n"] == 1
    assert exc_info.value.status_code == 403
    assert "permission" in exc_info.value.message.lower()


def test_documents_fetched_once_and_cached():
    """get_number_of_documents() followed by read_all_documents() must not
    crawl GitHub's API twice."""
    page = _issues_page([_issue_node(1, "First")], has_next=False, end_cursor=None)
    calls = {"n": 0}

    def router(body):
        calls["n"] += 1
        return FakeResponse(200, page)

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        reader = _reader()
        count = reader.get_number_of_documents()
        docs = list(reader.read_all_documents())

    assert count == 1
    assert len(docs) == 1
    assert calls["n"] == 1
