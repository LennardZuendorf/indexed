"""Comment evidence must be complete or say it is not (#356).

The reader used to embed `comments(first: 100)` and stop, so comment 120 of a
150-comment issue was invisible and nothing in the payload said so.
"""

import math
from unittest.mock import patch

import pytest

from indexed.connectors.github import queries
from indexed.connectors.github.github_graphql_reader import (
    MAX_COMMENT_PAGES,
    GitHubGraphQLReader,
)
from ._fakes import FakeAsyncClient, FakeResponse

pytestmark = pytest.mark.unit


def _issue_page(node: dict) -> dict:
    return {
        "data": {
            "repository": {
                "issues": {
                    "nodes": [node],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }


def _pr_page(node: dict) -> dict:
    return {
        "data": {
            "repository": {
                "pullRequests": {
                    "nodes": [node],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }


def _thread_node(number: int, kind: str, total: int) -> dict:
    return {
        "id": f"I_{number}",
        "number": number,
        "title": f"{kind} thread #{number}",
        "body": "Body",
        "state": "OPEN",
        "url": f"https://github.com/octo/hello/{kind}/{number}",
        "updatedAt": "2026-06-20T10:00:00Z",
        "createdAt": "2026-06-19T10:00:00Z",
        "author": {"login": "octocat"},
        "labels": {"nodes": []},
        "comments": _comment_connection(1, min(100, total), total),
    }


def _comment_node(n: int) -> dict:
    return {
        "id": f"IC_{n}",
        "url": f"https://github.com/octo/hello/issues/1#issuecomment-{n}",
        "author": {"login": "dev"},
        "body": f"comment {n}",
        "createdAt": "2026-06-20T12:00:00Z",
    }


def _comment_connection(start: int, end: int, total: int) -> dict:
    return {
        "nodes": [_comment_node(n) for n in range(start, end + 1)],
        "pageInfo": {
            "hasNextPage": end < total,
            "endCursor": f"comment-cursor-{end}" if end < total else None,
        },
    }


def _thread_router(total: int, requests: list[dict], kind: str = "issues"):
    """One issue (or PR) with `total` comments. The thread page embeds comments
    1-100; every page after that is served by COMMENT_PAGE_QUERY, cursor-driven."""

    def router(body):
        requests.append(body)
        query = body["query"]
        if query == queries.ISSUES_QUERY:
            node = _thread_node(1, "issues", total)
            return FakeResponse(200, _issue_page(node))
        if query == queries.PULL_REQUESTS_QUERY:
            node = _thread_node(4, "pull", total)
            return FakeResponse(200, _pr_page(node))
        assert query == queries.COMMENT_PAGE_QUERY, query
        after = int(body["variables"]["after"].rsplit("-", 1)[1])
        return FakeResponse(
            200,
            {
                "data": {
                    "node": {
                        "comments": _comment_connection(
                            after + 1, min(after + 100, total), total
                        )
                    }
                }
            },
        )

    return router


def _reader(**overrides) -> GitHubGraphQLReader:
    kwargs = dict(
        graphql_url="https://api.github.com/graphql",
        token="ghp_test",
        host="github.com",
        repos=[("octo", "hello")],
        project=None,
        state="all",
        labels=None,
        include_pull_requests=False,
        include_comments=True,
        page_size=100,
        max_concurrent_requests=2,
        number_of_retries=3,
        retry_delay=0.0,
    )
    kwargs.update(overrides)
    return GitHubGraphQLReader(**kwargs)


def _run(reader: GitHubGraphQLReader, router):
    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        return list(reader.read_all_documents())


def test_comment_past_the_first_page_is_retrieved():
    """The only relevant comment sits at #120 of 150: it must be indexed."""
    requests: list[dict] = []

    (doc,) = _run(_reader(), _thread_router(150, requests))

    ids = [c["id"] for c in doc["comments"]]
    assert "IC_120" in ids
    assert len(ids) == 150
    assert len(set(ids)) == len(ids), "pages must not duplicate comment ids"
    assert "commentsTruncated" not in doc


def test_issue_requests_stay_under_the_stated_ceiling():
    """Ceiling for a 150-comment issue: the thread page + one comment page,
    i.e. `1 + ceil((150 - 100) / 100)` = 2 requests."""
    requests: list[dict] = []

    _run(_reader(), _thread_router(150, requests))

    ceiling = 1 + math.ceil((150 - 100) / 100)
    assert len(requests) == ceiling
    assert len(requests) <= ceiling


def test_comment_pages_are_deduplicated_by_id():
    """Overlapping pages (a comment added between requests shifts the window)
    must not produce duplicate ids in the payload."""

    def router(body):
        if body["query"] == queries.ISSUES_QUERY:
            return FakeResponse(200, _issue_page(_thread_node(1, "issues", 150)))
        # Deliberately re-include the last comment of the previous page.
        return FakeResponse(
            200,
            {
                "data": {
                    "node": {
                        "comments": _comment_connection(100, 150, 150),
                    }
                }
            },
        )

    (doc,) = _run(_reader(), router)
    ids = [c["id"] for c in doc["comments"]]
    assert len(ids) == 150
    assert len(set(ids)) == 150


def test_cap_declares_truncation_instead_of_silence():
    """Past the page cap the payload must report incomplete coverage and the
    limit it applied — silence is the failure. The request count stays bounded."""
    requests: list[dict] = []

    (doc,) = _run(_reader(), _thread_router(5_000, requests))

    assert len(requests) == MAX_COMMENT_PAGES
    assert doc["commentsTruncated"] is True
    assert doc["commentsLimit"] == MAX_COMMENT_PAGES * 100
    assert len(doc["comments"]) == MAX_COMMENT_PAGES * 100


def test_pull_request_comments_also_paginate():
    requests: list[dict] = []

    docs = _run(
        _reader(include_pull_requests=True),
        _thread_router(150, requests, kind="pull"),
    )
    doc = next(d for d in docs if d["kind"] == "pull_request")

    assert len(doc["comments"]) == 150
    assert doc["comments"][-1]["id"] == "IC_150"


def test_vanished_thread_marks_truncation_instead_of_failing():
    """A thread deleted between its list page and its comment page answers
    `node: null` + NOT_FOUND; that must be reported as truncation, not raise."""

    def router(body):
        if body["query"] == queries.ISSUES_QUERY:
            return FakeResponse(200, _issue_page(_thread_node(1, "issues", 150)))
        return FakeResponse(
            200,
            {
                "data": {"node": None},
                "errors": [{"type": "NOT_FOUND", "path": ["node"]}],
            },
        )

    (doc,) = _run(_reader(), router)

    assert len(doc["comments"]) == 100
    assert doc["commentsTruncated"] is True
    assert doc["commentsLimit"] == 100


def test_overlapping_repo_and_project_thread_paginates_once():
    """The same 150-comment thread reached from `repos` and a project board
    must cost one comment page, not one per source: dedupe runs before
    pagination."""
    requests: list[dict] = []

    def router(body):
        requests.append(body)
        query = body["query"]
        node = _thread_node(1, "issues", 150)
        if query == queries.ISSUES_QUERY:
            return FakeResponse(200, _issue_page(node))
        if query == queries.PROJECT_ITEMS_QUERY:
            node["repository"] = {"owner": {"login": "octo"}, "name": "hello"}
            return FakeResponse(
                200,
                {
                    "data": {
                        "organization": {
                            "projectV2": {
                                "items": {
                                    "nodes": [
                                        {
                                            "id": "PVTI_1",
                                            "content": {
                                                **node,
                                                "__typename": "Issue",
                                            },
                                            "fieldValues": {"nodes": []},
                                        }
                                    ],
                                    "pageInfo": {
                                        "hasNextPage": False,
                                        "endCursor": None,
                                    },
                                }
                            }
                        }
                    }
                },
            )
        return FakeResponse(
            200,
            {"data": {"node": {"comments": _comment_connection(101, 150, 150)}}},
        )

    docs = _run(_reader(project=("octo", 12)), router)

    assert len(docs) == 1
    assert len(docs[0]["comments"]) == 150
    comment_pages = [r for r in requests if r["query"] == queries.COMMENT_PAGE_QUERY]
    assert len(comment_pages) == 1
