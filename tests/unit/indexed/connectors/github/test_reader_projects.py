from unittest.mock import patch

from indexed.connectors.github.github_graphql_reader import GitHubGraphQLReader
from ._fakes import FakeAsyncClient, FakeResponse


def _reader(**overrides) -> GitHubGraphQLReader:
    kwargs = dict(
        graphql_url="https://api.github.com/graphql",
        token="ghp_test",
        repos=[],
        project=("octo", 12),
        state="all",
        labels=None,
        include_pull_requests=True,
        include_comments=True,
        page_size=10,
        max_concurrent_requests=2,
        number_of_retries=1,
        retry_delay=0.0,
    )
    kwargs.update(overrides)
    return GitHubGraphQLReader(**kwargs)


def _pr_page(nodes, has_next=False, end_cursor=None):
    return {
        "data": {
            "repository": {
                "pullRequests": {
                    "nodes": nodes,
                    "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
                }
            }
        }
    }


def _issues_empty_page():
    return {
        "data": {
            "repository": {
                "issues": {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }


def _project_probe_org():
    return {
        "data": {
            "organization": {
                "projectV2": {
                    "items": {
                        "nodes": [],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }
    }


def test_pull_requests_included_when_enabled():
    pr_node = {
        "id": "PR_1",
        "number": 5,
        "title": "Fix retry",
        "body": "desc",
        "state": "OPEN",
        "url": "https://github.com/octo/api/pull/5",
        "updatedAt": "2026-06-20T10:00:00Z",
        "createdAt": "2026-06-19T10:00:00Z",
        "author": {"login": "octocat"},
        "labels": {"nodes": []},
        "comments": {"nodes": []},
    }

    def router(body):
        if "pullRequests" in body["query"]:
            return FakeResponse(200, _pr_page([pr_node]))
        return FakeResponse(200, _issues_empty_page())

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        docs = list(_reader(repos=[("octo", "api")], project=None).read_all_documents())

    assert len(docs) == 1
    assert docs[0]["kind"] == "pull_request"
    assert docs[0]["id"] == "octo/api#5"


def test_pull_requests_omitted_when_disabled():
    def router(body):
        return FakeResponse(200, _issues_empty_page())

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        docs = list(
            _reader(
                repos=[("octo", "api")], project=None, include_pull_requests=False
            ).read_all_documents()
        )

    assert docs == []


def test_pull_request_state_filter_passed_as_variables():
    captured = []

    def router(body):
        if "pullRequests" in body["query"]:
            captured.append(body["variables"]["states"])
            return FakeResponse(200, _pr_page([]))
        return FakeResponse(200, _issues_empty_page())

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        list(
            _reader(
                repos=[("octo", "api")], project=None, state="open"
            ).read_all_documents()
        )
        list(
            _reader(
                repos=[("octo", "api")], project=None, state="closed"
            ).read_all_documents()
        )

    assert captured == [["OPEN"], ["CLOSED", "MERGED"]]


def test_project_items_two_repos_with_field_values():
    issue_node = {
        "__typename": "Issue",
        "id": "I_9",
        "number": 9,
        "title": "Board issue",
        "body": "b",
        "state": "OPEN",
        "url": "https://github.com/octo/web/issues/9",
        "updatedAt": "2026-06-20T10:00:00Z",
        "createdAt": "2026-06-19T10:00:00Z",
        "author": {"login": "octocat"},
        "repository": {"owner": {"login": "octo"}, "name": "web"},
        "labels": {"nodes": []},
        "comments": {"nodes": []},
    }
    item_node = {
        "id": "PVTI_1",
        "fieldValues": {
            "nodes": [
                {"name": "In Progress", "field": {"name": "Status"}},
                {"text": "release notes", "field": {"name": "Notes"}},
                {"name": "orphaned", "field": {}},
            ]
        },
        "content": issue_node,
    }

    probe_calls = {"n": 0}

    def router(body):
        variables = body["variables"]
        if "organization" in body["query"] and variables.get("first") == 1:
            probe_calls["n"] += 1
            return FakeResponse(200, _project_probe_org())
        if "organization" in body["query"]:
            return FakeResponse(
                200,
                {
                    "data": {
                        "organization": {
                            "projectV2": {
                                "items": {
                                    "nodes": [item_node],
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
        return FakeResponse(200, _issues_empty_page())

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        docs = list(
            _reader(
                repos=[], project=("octo", 12), include_pull_requests=False
            ).read_all_documents()
        )

    assert len(docs) == 1
    assert docs[0]["id"] == "octo/web#9"
    assert docs[0]["project_fields"] == {
        "Status": "In Progress",
        "Notes": "release notes",
    }
    assert probe_calls["n"] == 1


def test_draft_project_item_indexed_standalone():
    draft_node = {
        "__typename": "DraftIssue",
        "title": "Investigate flaky test",
        "body": "notes",
        "createdAt": "2026-06-19T10:00:00Z",
        "updatedAt": "2026-06-20T10:00:00Z",
    }
    item_node = {"id": "PVTI_2", "fieldValues": {"nodes": []}, "content": draft_node}

    def router(body):
        variables = body["variables"]
        if "organization" in body["query"] and variables.get("first") == 1:
            return FakeResponse(200, _project_probe_org())
        if "organization" in body["query"]:
            return FakeResponse(
                200,
                {
                    "data": {
                        "organization": {
                            "projectV2": {
                                "items": {
                                    "nodes": [item_node],
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
        return FakeResponse(200, _issues_empty_page())

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        docs = list(
            _reader(
                repos=[], project=("octo", 12), include_pull_requests=False
            ).read_all_documents()
        )

    assert len(docs) == 1
    assert docs[0]["kind"] == "draft"
    assert docs[0]["id"] == "project:PVTI_2"
    assert docs[0]["title"] == "Investigate flaky test"


def test_issue_in_both_repos_and_project_deduped():
    issue_node = {
        "__typename": "Issue",
        "id": "I_9",
        "number": 9,
        "title": "Board issue",
        "body": "b",
        "state": "OPEN",
        "url": "https://github.com/octo/web/issues/9",
        "updatedAt": "2026-06-20T10:00:00Z",
        "createdAt": "2026-06-19T10:00:00Z",
        "author": {"login": "octocat"},
        "repository": {"owner": {"login": "octo"}, "name": "web"},
        "labels": {"nodes": []},
        "comments": {"nodes": []},
    }
    item_node = {"id": "PVTI_1", "fieldValues": {"nodes": []}, "content": issue_node}
    repo_issue_page = {
        "data": {
            "repository": {
                "issues": {
                    "nodes": [issue_node],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }

    def router(body):
        variables = body["variables"]
        if "organization" in body["query"] and variables.get("first") == 1:
            return FakeResponse(200, _project_probe_org())
        if "organization" in body["query"]:
            return FakeResponse(
                200,
                {
                    "data": {
                        "organization": {
                            "projectV2": {
                                "items": {
                                    "nodes": [item_node],
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
        return FakeResponse(200, repo_issue_page)

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        docs = list(
            _reader(
                repos=[("octo", "web")],
                project=("octo", 12),
                include_pull_requests=False,
            ).read_all_documents()
        )

    assert len(docs) == 1
    assert docs[0]["id"] == "octo/web#9"


def test_user_owned_project_uses_user_query():
    issue_node = {
        "__typename": "Issue",
        "id": "I_3",
        "number": 3,
        "title": "User board issue",
        "body": "b",
        "state": "OPEN",
        "url": "https://github.com/octo/web/issues/3",
        "updatedAt": "2026-06-20T10:00:00Z",
        "createdAt": "2026-06-19T10:00:00Z",
        "author": {"login": "octocat"},
        "repository": {"owner": {"login": "octo"}, "name": "web"},
        "labels": {"nodes": []},
        "comments": {"nodes": []},
    }
    item_node = {"id": "PVTI_3", "fieldValues": {"nodes": []}, "content": issue_node}

    def router(body):
        variables = body["variables"]
        if variables.get("first") == 1:
            return FakeResponse(200, {"data": {"organization": None}})
        if "user(login" in body["query"]:
            return FakeResponse(
                200,
                {
                    "data": {
                        "user": {
                            "projectV2": {
                                "items": {
                                    "nodes": [item_node],
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
        return FakeResponse(200, _issues_empty_page())

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        docs = list(
            _reader(
                repos=[], project=("octocat", 7), include_pull_requests=False
            ).read_all_documents()
        )

    assert len(docs) == 1
    assert docs[0]["id"] == "octo/web#3"


def test_project_item_with_null_content_is_skipped():
    redacted_item = {"id": "PVTI_4", "fieldValues": {"nodes": []}, "content": None}

    def router(body):
        variables = body["variables"]
        if "organization" in body["query"] and variables.get("first") == 1:
            return FakeResponse(200, _project_probe_org())
        if "organization" in body["query"]:
            return FakeResponse(
                200,
                {
                    "data": {
                        "organization": {
                            "projectV2": {
                                "items": {
                                    "nodes": [redacted_item],
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
        return FakeResponse(200, _issues_empty_page())

    with patch(
        "indexed.connectors.github.github_graphql_reader.httpx.AsyncClient",
        new=lambda **kw: FakeAsyncClient(router, **kw),
    ):
        docs = list(
            _reader(
                repos=[], project=("octo", 12), include_pull_requests=False
            ).read_all_documents()
        )

    assert docs == []
