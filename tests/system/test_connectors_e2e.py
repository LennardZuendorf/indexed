"""End-to-end system tests for Jira and Confluence connectors.

These tests exercise the full reader -> converter -> v1 indexed document pipeline
using mocked API responses (no real Jira/Confluence instances needed).
"""

from __future__ import annotations

from typing import Any

import pytest

from indexed.connectors.confluence.unified_confluence_document_converter import (
    UnifiedConfluenceDocumentConverter,
)
from indexed.connectors.confluence.confluence_document_reader import (
    ConfluenceDocumentReader,
)
from indexed.connectors.jira.unified_jira_document_converter import (
    UnifiedJiraDocumentConverter,
)
from indexed.connectors.jira.unified_jira_document_reader import (
    JiraAuthType,
    UnifiedJiraDocumentReader,
)
from indexed.connectors.github.connector import GitHubConnector
from indexed.connectors.github.schema import GitHubConfig

pytestmark = pytest.mark.connectors


# ---------------------------------------------------------------------------
# Helpers: Fake Jira
# ---------------------------------------------------------------------------


def _make_fake_jira_class(issues: list[dict[str, Any]]):
    """Create a fake Jira class that returns the given issues from jql()."""

    class _FakeJira:
        def __init__(self, **kwargs: Any) -> None:
            self._issues = issues

        def jql(
            self,
            jql: str,
            fields: str | list[str] | None = None,
            start: int = 0,
            limit: int = 50,
            expand: str | list[str] | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            batch = self._issues[start : start + limit]
            return {
                "issues": batch,
                "total": len(self._issues),
                "startAt": start,
                "maxResults": limit,
            }

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
            batch = (
                self._issues[start : start + limit] if limit else self._issues[start:]
            )
            result: dict[str, Any] = {"issues": batch}
            next_start = start + len(batch)
            if next_start < len(self._issues):
                result["nextPageToken"] = str(next_start)
            return result

        def approximate_issue_count(self, jql: str) -> dict[str, Any]:
            return {"count": len(self._issues)}

    return _FakeJira


def _make_adf_text(text: str) -> dict[str, Any]:
    """Create a simple ADF paragraph containing the given text."""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def _make_jira_issue(
    key: str,
    summary: str,
    base_url: str = "https://acme.atlassian.net",
    description: dict[str, Any] | str | None = None,
    comments: list[dict[str, Any]] | None = None,
    updated: str = "2026-01-15T10:00:00.000+0000",
) -> dict[str, Any]:
    """Build a realistic Jira issue dict."""
    return {
        "key": key,
        "self": f"{base_url}/rest/api/2/issue/{key.split('-')[-1]}",
        "fields": {
            "summary": summary,
            "updated": updated,
            "description": description,
            "comment": {"comments": comments or []},
        },
    }


# ---------------------------------------------------------------------------
# Helpers: Fake Confluence HTTP responses
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal requests.Response stand-in."""

    def __init__(self, json_data: dict[str, Any]) -> None:
        self._json = json_data
        self.status_code = 200

    def json(self) -> dict[str, Any]:
        return self._json

    def raise_for_status(self) -> None:
        pass


def _make_fake_confluence_get(pages: list[dict[str, Any]]):
    """Return a function that mimics requests.get for the Confluence reader."""

    def fake_get(
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        auth: Any = None,
        **kwargs: Any,
    ) -> _FakeResponse:
        params = params or {}
        start = params.get("start", 0)
        limit = params.get("limit", 50)
        batch = pages[start : start + limit]
        return _FakeResponse({"results": batch, "totalSize": len(pages)})

    return fake_get


def _make_confluence_page(
    page_id: str = "12345",
    title: str = "My Page",
    ancestors: list[dict] | None = None,
    body_html: str = "<p>Page content.</p>",
    comments_html: list[str] | None = None,
    updated: str = "2026-01-15T10:00:00.000Z",
    base_url: str = "https://confluence.example.com",
    webui: str = "/display/SPACE/My+Page",
) -> dict:
    """Build a realistic Confluence page dict as returned by the search API."""
    comment_results = [
        {"body": {"storage": {"value": html}}} for html in (comments_html or [])
    ]
    return {
        "id": page_id,
        "title": title,
        "ancestors": ancestors if ancestors is not None else [],
        "body": {"storage": {"value": body_html}},
        "version": {"when": updated},
        "_links": {
            "self": f"{base_url}/rest/api/content/{page_id}",
            "webui": webui,
        },
        "children": {
            "comment": {
                "size": len(comment_results),
                "results": comment_results,
            }
        },
    }


# ---------------------------------------------------------------------------
# Helpers: Fake GitHub GraphQL
# ---------------------------------------------------------------------------


class _FakeGitHubResponse:
    """Minimal httpx.Response stand-in."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        pass


class _FakeGitHubAsyncClient:
    """Stands in for httpx.AsyncClient; routes each GraphQL POST body to a
    canned response via `router`."""

    def __init__(self, router: Any, **kwargs: Any) -> None:
        self._router = router

    async def __aenter__(self) -> "_FakeGitHubAsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def post(self, url: str, **kwargs: Any) -> _FakeGitHubResponse:
        return self._router(kwargs.get("json", {}))


_EMPTY_PAGE_INFO = {"hasNextPage": False, "endCursor": None}


def _make_github_router(
    issues_page: dict[str, Any] | None = None,
    pr_page: dict[str, Any] | None = None,
):
    """Route a GraphQL request body to a canned issues or pull-requests page,
    based on the operation name in the query string."""
    empty_issues = {
        "repository": {"issues": {"nodes": [], "pageInfo": _EMPTY_PAGE_INFO}}
    }
    empty_prs = {
        "repository": {"pullRequests": {"nodes": [], "pageInfo": _EMPTY_PAGE_INFO}}
    }

    def router(body: dict[str, Any]) -> _FakeGitHubResponse:
        query = body.get("query", "")
        if "query PullRequests" in query:
            return _FakeGitHubResponse({"data": pr_page or empty_prs})
        return _FakeGitHubResponse({"data": issues_page or empty_issues})

    return router


def _github_issue_node(
    number: int,
    title: str,
    body: str = "",
    labels: list[str] | None = None,
    comment_nodes: list[dict[str, Any]] | None = None,
    state: str = "OPEN",
) -> dict[str, Any]:
    """Build a realistic GitHub issue/PR GraphQL node."""
    return {
        "id": f"I_{number}",
        "number": number,
        "title": title,
        "body": body,
        "state": state,
        "url": f"https://github.com/octo/hello/issues/{number}",
        "updatedAt": "2026-06-20T10:00:00Z",
        "createdAt": "2026-06-19T10:00:00Z",
        "author": {"login": "octocat"},
        "labels": {"nodes": [{"name": name} for name in (labels or [])]},
        "comments": {"nodes": comment_nodes or []},
    }


def _github_issues_page(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"repository": {"issues": {"nodes": nodes, "pageInfo": _EMPTY_PAGE_INFO}}}


def _github_pull_requests_page(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "repository": {"pullRequests": {"nodes": nodes, "pageInfo": _EMPTY_PAGE_INFO}}
    }


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _run_jira_pipeline(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw issues through the Jira converter and return v1 docs."""
    converter = UnifiedJiraDocumentConverter()
    return [converter.convert(issue)[0] for issue in issues]


def _run_confluence_pipeline(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw reader output through the Confluence converter."""
    converter = UnifiedConfluenceDocumentConverter(is_cloud=False)
    return [converter.convert(doc)[0] for doc in documents]


def _run_github_pipeline(
    documents: list[dict[str, Any]], converter: Any
) -> list[dict[str, Any]]:
    """Convert raw GitHub documents through the given converter."""
    return [next(converter.convert(doc)) for doc in documents]


# ===========================================================================
# Jira Connector E2E Tests
# ===========================================================================


class TestJiraConnectorE2E:
    """Full pipeline tests: mock Jira -> reader -> converter -> v1 output."""

    def test_full_pipeline_cloud_adf(self, monkeypatch):
        """Cloud issue with ADF description and comments produces valid v1 output."""
        import indexed.connectors.jira.unified_jira_document_reader as mod

        adf_description = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Overview"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "This is the description."}],
                },
            ],
        }
        adf_comment = _make_adf_text("Great work on this ticket.")
        issue = _make_jira_issue(
            "CLOUD-1",
            "Fix login bug",
            description=adf_description,
            comments=[{"body": adf_comment}],
        )
        monkeypatch.setattr(mod, "Jira", _make_fake_jira_class([issue]))

        reader = UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",
            query="project = TEST",
            auth_type=JiraAuthType.CLOUD,
            email="x@acme.com",
            api_token="fake",
            batch_size=10,
            retry_delay=0,
            number_of_retries=1,
        )
        docs = _run_jira_pipeline(list(reader.read_all_documents()))

        assert len(docs) == 1
        doc = docs[0]
        assert doc["id"] == "CLOUD-1"
        assert doc["url"].endswith("/browse/CLOUD-1")
        assert doc["modifiedTime"] == "2026-01-15T10:00:00.000+0000"
        assert "## Overview" in doc["text"]
        assert "This is the description." in doc["text"]
        assert "Great work on this ticket." in doc["text"]
        assert doc["chunks"][0]["indexedData"] == "CLOUD-1 : Fix login bug"

    def test_full_pipeline_server_plain_text(self, monkeypatch):
        """Server issue with plain text description produces valid v1 output."""
        import indexed.connectors.jira.unified_jira_document_reader as mod

        issue = _make_jira_issue(
            "SRV-42",
            "Update config",
            base_url="https://jira.corp.example.com",
            description="Please update the database config for staging.",
            comments=[{"body": "Done, deployed to staging."}],
        )
        monkeypatch.setattr(mod, "Jira", _make_fake_jira_class([issue]))

        reader = UnifiedJiraDocumentReader(
            base_url="https://jira.corp.example.com",
            query="project = APP",
            auth_type=JiraAuthType.SERVER_TOKEN,
            token="pat-token",
            batch_size=10,
            retry_delay=0,
            number_of_retries=1,
        )
        docs = _run_jira_pipeline(list(reader.read_all_documents()))

        assert len(docs) == 1
        doc = docs[0]
        assert doc["id"] == "SRV-42"
        assert "jira.corp.example.com/browse/SRV-42" in doc["url"]
        assert "Please update the database config for staging." in doc["text"]
        assert "Done, deployed to staging." in doc["text"]

    def test_pagination_multiple_issues(self, monkeypatch):
        """Multiple issues with batch_size=1 all come through via pagination."""
        import indexed.connectors.jira.unified_jira_document_reader as mod

        issues = [_make_jira_issue(f"PAG-{i}", f"Issue {i}") for i in range(1, 4)]
        monkeypatch.setattr(mod, "Jira", _make_fake_jira_class(issues))

        reader = UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",
            query="project = PAG",
            auth_type=JiraAuthType.CLOUD,
            email="x@acme.com",
            api_token="fake",
            batch_size=1,
            retry_delay=0,
            number_of_retries=1,
        )
        raw_docs = list(reader.read_all_documents())
        docs = _run_jira_pipeline(raw_docs)

        assert len(docs) == 3
        assert [d["id"] for d in docs] == ["PAG-1", "PAG-2", "PAG-3"]

    def test_empty_description_no_crash(self, monkeypatch):
        """Issue with None description does not crash; chunks have ticket info."""
        import indexed.connectors.jira.unified_jira_document_reader as mod

        issue = _make_jira_issue("EMPTY-1", "No description issue", description=None)
        monkeypatch.setattr(mod, "Jira", _make_fake_jira_class([issue]))

        reader = UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",
            query="project = TEST",
            auth_type=JiraAuthType.CLOUD,
            email="x@acme.com",
            api_token="fake",
            retry_delay=0,
            number_of_retries=1,
        )
        docs = _run_jira_pipeline(list(reader.read_all_documents()))

        assert len(docs) == 1
        doc = docs[0]
        assert doc["id"] == "EMPTY-1"
        assert len(doc["chunks"]) >= 1
        assert "EMPTY-1 : No description issue" in doc["text"]

    def test_multiple_comments(self, monkeypatch):
        """Issue with multiple comments includes all comment text."""
        import indexed.connectors.jira.unified_jira_document_reader as mod

        comments = [
            {"body": _make_adf_text("First comment.")},
            {"body": _make_adf_text("Second comment.")},
            {"body": _make_adf_text("Third comment.")},
        ]
        issue = _make_jira_issue(
            "CMT-1", "Comment test", description=None, comments=comments
        )
        monkeypatch.setattr(mod, "Jira", _make_fake_jira_class([issue]))

        reader = UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",
            query="project = TEST",
            auth_type=JiraAuthType.CLOUD,
            email="x@acme.com",
            api_token="fake",
            retry_delay=0,
            number_of_retries=1,
        )
        docs = _run_jira_pipeline(list(reader.read_all_documents()))

        doc = docs[0]
        assert "First comment." in doc["text"]
        assert "Second comment." in doc["text"]
        assert "Third comment." in doc["text"]
        # Ticket info chunk + at least one content chunk
        assert len(doc["chunks"]) >= 2

    def test_output_structure(self, monkeypatch):
        """Converted output has correct keys and value types."""
        import indexed.connectors.jira.unified_jira_document_reader as mod

        issue = _make_jira_issue("STR-1", "Structure test", description="Some text")
        monkeypatch.setattr(mod, "Jira", _make_fake_jira_class([issue]))

        reader = UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",
            query="project = TEST",
            auth_type=JiraAuthType.CLOUD,
            email="x@acme.com",
            api_token="fake",
            retry_delay=0,
            number_of_retries=1,
        )
        docs = _run_jira_pipeline(list(reader.read_all_documents()))

        assert len(docs) == 1
        doc = docs[0]
        assert set(doc.keys()) == {"id", "url", "modifiedTime", "text", "chunks"}
        assert isinstance(doc["id"], str)
        assert isinstance(doc["url"], str)
        assert doc["url"].startswith("https://")
        assert isinstance(doc["modifiedTime"], str)
        assert isinstance(doc["text"], str)
        assert isinstance(doc["chunks"], list)
        assert len(doc["chunks"]) > 0
        for chunk in doc["chunks"]:
            assert "indexedData" in chunk
            assert isinstance(chunk["indexedData"], str)

    def test_first_chunk_is_ticket_info(self, monkeypatch):
        """First chunk is always 'KEY : Summary'."""
        import indexed.connectors.jira.unified_jira_document_reader as mod

        issue = _make_jira_issue(
            "TIK-42",
            "My Summary",
            description="Extra content here for chunking purposes.",
        )
        monkeypatch.setattr(mod, "Jira", _make_fake_jira_class([issue]))

        reader = UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",
            query="project = TEST",
            auth_type=JiraAuthType.CLOUD,
            email="x@acme.com",
            api_token="fake",
            retry_delay=0,
            number_of_retries=1,
        )
        docs = _run_jira_pipeline(list(reader.read_all_documents()))

        assert docs[0]["chunks"][0]["indexedData"] == "TIK-42 : My Summary"

    def test_adf_text_extraction(self, monkeypatch):
        """ADF with headings, bold, italic, lists, and code extracts correctly."""
        import indexed.connectors.jira.unified_jira_document_reader as mod

        adf_description = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": "Main Heading"}],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "bold text",
                            "marks": [{"type": "strong"}],
                        },
                        {"type": "text", "text": " and "},
                        {
                            "type": "text",
                            "text": "italic text",
                            "marks": [{"type": "em"}],
                        },
                    ],
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "item one"}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "item two"}],
                                }
                            ],
                        },
                    ],
                },
                {
                    "type": "codeBlock",
                    "content": [{"type": "text", "text": "print('hello')"}],
                },
            ],
        }
        issue = _make_jira_issue(
            "ADF-1", "ADF extraction test", description=adf_description
        )
        monkeypatch.setattr(mod, "Jira", _make_fake_jira_class([issue]))

        reader = UnifiedJiraDocumentReader(
            base_url="https://acme.atlassian.net",
            query="project = TEST",
            auth_type=JiraAuthType.CLOUD,
            email="x@acme.com",
            api_token="fake",
            retry_delay=0,
            number_of_retries=1,
        )
        docs = _run_jira_pipeline(list(reader.read_all_documents()))

        text = docs[0]["text"]
        assert "# Main Heading" in text
        assert "**bold text**" in text
        assert "*italic text*" in text
        assert "- item one" in text
        assert "- item two" in text
        assert "```" in text
        assert "print('hello')" in text


# ===========================================================================
# Confluence Connector E2E Tests
# ===========================================================================


class TestConfluenceConnectorE2E:
    """Full pipeline tests: mock HTTP -> reader -> converter -> v1 output."""

    def test_full_pipeline(self, monkeypatch):
        """Page with HTML body and comments produces valid v1 output."""
        import indexed.connectors.confluence.confluence_document_reader as mod

        page = _make_confluence_page(
            page_id="101",
            title="Setup Guide",
            ancestors=[{"title": "Documentation"}],
            body_html="<h2>Getting Started</h2><p>Install the package.</p>",
            comments_html=["<p>Thanks for the guide!</p>"],
        )
        monkeypatch.setattr(mod.requests, "get", _make_fake_confluence_get([page]))

        reader = ConfluenceDocumentReader(
            base_url="https://confluence.example.com",
            query="space = DOCS",
            token="fake-token",
            batch_size=50,
            number_of_retries=1,
            retry_delay=0,
            read_all_comments=False,
        )
        docs = _run_confluence_pipeline(reader.read_all_documents())

        assert len(docs) == 1
        doc = docs[0]
        assert doc["id"] == "101"
        assert "confluence.example.com" in doc["url"]
        assert doc["modifiedTime"] == "2026-01-15T10:00:00.000Z"
        assert "Getting Started" in doc["text"]
        assert "Install the package." in doc["text"]
        assert "Thanks for the guide!" in doc["text"]
        assert doc["chunks"][0]["indexedData"] == "Documentation -> Setup Guide"

    def test_html_body_extraction(self, monkeypatch):
        """HTML with headings and paragraphs extracts clean text."""
        import indexed.connectors.confluence.confluence_document_reader as mod

        page = _make_confluence_page(
            body_html="<h1>Title</h1><p>Paragraph one.</p><p>Paragraph two.</p>",
        )
        monkeypatch.setattr(mod.requests, "get", _make_fake_confluence_get([page]))

        reader = ConfluenceDocumentReader(
            base_url="https://confluence.example.com",
            query="space = TEST",
            token="fake-token",
            number_of_retries=1,
            retry_delay=0,
            read_all_comments=False,
        )
        docs = _run_confluence_pipeline(reader.read_all_documents())

        text = docs[0]["text"]
        assert "Title" in text
        assert "Paragraph one." in text
        assert "Paragraph two." in text
        # No HTML tags in output
        assert "<h1>" not in text
        assert "<p>" not in text

    def test_ancestors_title_path(self, monkeypatch):
        """Page with ancestors builds correct title path in first chunk."""
        import indexed.connectors.confluence.confluence_document_reader as mod

        page = _make_confluence_page(
            title="Leaf Page",
            ancestors=[{"title": "Root"}, {"title": "Section"}],
        )
        monkeypatch.setattr(mod.requests, "get", _make_fake_confluence_get([page]))

        reader = ConfluenceDocumentReader(
            base_url="https://confluence.example.com",
            query="space = TEST",
            token="fake-token",
            number_of_retries=1,
            retry_delay=0,
            read_all_comments=False,
        )
        docs = _run_confluence_pipeline(reader.read_all_documents())

        assert docs[0]["chunks"][0]["indexedData"] == "Root -> Section -> Leaf Page"

    def test_page_with_comments(self, monkeypatch):
        """Page with comments includes comment text in output."""
        import indexed.connectors.confluence.confluence_document_reader as mod

        page = _make_confluence_page(
            body_html="<p>Main content.</p>",
            comments_html=[
                "<p>Comment A</p>",
                "<p>Comment B</p>",
            ],
        )
        monkeypatch.setattr(mod.requests, "get", _make_fake_confluence_get([page]))

        reader = ConfluenceDocumentReader(
            base_url="https://confluence.example.com",
            query="space = TEST",
            token="fake-token",
            number_of_retries=1,
            retry_delay=0,
            read_all_comments=False,
        )
        docs = _run_confluence_pipeline(reader.read_all_documents())

        text = docs[0]["text"]
        assert "Comment A" in text
        assert "Comment B" in text

    def test_empty_body_no_crash(self, monkeypatch):
        """Page with empty body does not crash."""
        import indexed.connectors.confluence.confluence_document_reader as mod

        page = _make_confluence_page(body_html="", title="Empty Page")
        monkeypatch.setattr(mod.requests, "get", _make_fake_confluence_get([page]))

        reader = ConfluenceDocumentReader(
            base_url="https://confluence.example.com",
            query="space = TEST",
            token="fake-token",
            number_of_retries=1,
            retry_delay=0,
            read_all_comments=False,
        )
        docs = _run_confluence_pipeline(reader.read_all_documents())

        assert len(docs) == 1
        assert docs[0]["id"] == "12345"
        assert len(docs[0]["chunks"]) >= 1

    def test_multiple_pages(self, monkeypatch):
        """Multiple pages with batch_size=2 all get processed."""
        import indexed.connectors.confluence.confluence_document_reader as mod

        pages = [
            _make_confluence_page(
                page_id=str(i),
                title=f"Page {i}",
                body_html=f"<p>Content of page {i}.</p>",
                webui=f"/display/SPACE/Page+{i}",
            )
            for i in range(1, 4)
        ]
        monkeypatch.setattr(mod.requests, "get", _make_fake_confluence_get(pages))

        reader = ConfluenceDocumentReader(
            base_url="https://confluence.example.com",
            query="space = TEST",
            token="fake-token",
            batch_size=2,
            number_of_retries=1,
            retry_delay=0,
            read_all_comments=False,
        )
        docs = _run_confluence_pipeline(reader.read_all_documents())

        assert len(docs) == 3
        assert [d["id"] for d in docs] == ["1", "2", "3"]

    def test_output_structure(self, monkeypatch):
        """Converted output has correct keys and value types."""
        import indexed.connectors.confluence.confluence_document_reader as mod

        page = _make_confluence_page()
        monkeypatch.setattr(mod.requests, "get", _make_fake_confluence_get([page]))

        reader = ConfluenceDocumentReader(
            base_url="https://confluence.example.com",
            query="space = TEST",
            token="fake-token",
            number_of_retries=1,
            retry_delay=0,
            read_all_comments=False,
        )
        docs = _run_confluence_pipeline(reader.read_all_documents())

        assert len(docs) == 1
        doc = docs[0]
        assert set(doc.keys()) == {"id", "url", "modifiedTime", "text", "chunks"}
        assert isinstance(doc["id"], str)
        assert isinstance(doc["url"], str)
        assert doc["url"].startswith("https://")
        assert isinstance(doc["modifiedTime"], str)
        assert isinstance(doc["text"], str)
        assert isinstance(doc["chunks"], list)
        assert len(doc["chunks"]) > 0
        for chunk in doc["chunks"]:
            assert "indexedData" in chunk
            assert isinstance(chunk["indexedData"], str)


# ===========================================================================
# GitHub Connector E2E Tests
# ===========================================================================


class TestGitHubConnectorE2E:
    """Full pipeline tests: mock GraphQL transport -> GitHubConnector's real
    reader -> real converter -> v1 output."""

    def test_full_pipeline_issue_with_comments(self, monkeypatch):
        """Issue with labels and a comment produces valid v1 output via the
        connector's own reader + converter wiring."""
        import indexed.connectors.github.github_graphql_reader as mod

        node = _github_issue_node(
            7,
            "Search should handle unicode queries",
            body="Queries containing emoji or CJK characters currently 500.",
            labels=["bug", "search"],
            comment_nodes=[
                {
                    "author": {"login": "maintainer"},
                    "body": "Confirmed, working on a fix.",
                }
            ],
        )
        router = _make_github_router(issues_page=_github_issues_page([node]))
        monkeypatch.setattr(
            mod.httpx, "AsyncClient", lambda **kw: _FakeGitHubAsyncClient(router, **kw)
        )

        connector = GitHubConnector(
            GitHubConfig(repos=["octo/hello"], token="ghp_x", state="all")
        )
        docs = _run_github_pipeline(
            list(connector.reader.read_all_documents()), connector.converter
        )

        assert len(docs) == 1
        doc = docs[0]
        assert doc["id"] == "octo/hello#7"
        assert doc["url"] == "https://github.com/octo/hello/issues/7"
        assert doc["modifiedTime"] == "2026-06-20T10:00:00Z"
        assert (
            "Queries containing emoji or CJK characters currently 500." in doc["text"]
        )
        header = doc["chunks"][0]["indexedData"]
        assert "# Search should handle unicode queries" in header
        assert "State: OPEN" in header
        assert "bug, search" in header
        comment_chunk = doc["chunks"][-1]
        assert "Comment by maintainer:" in comment_chunk["indexedData"]
        assert "Confirmed, working on a fix." in comment_chunk["indexedData"]

    def test_pull_requests_included_when_configured(self, monkeypatch):
        """`include_pull_requests=True` reaches the reader and PR docs carry
        `kind: pull_request` through to converted chunk metadata."""
        import indexed.connectors.github.github_graphql_reader as mod

        issue_node = _github_issue_node(1, "An issue")
        pr_node = _github_issue_node(2, "A pull request", body="Fixes the bug.")
        router = _make_github_router(
            issues_page=_github_issues_page([issue_node]),
            pr_page=_github_pull_requests_page([pr_node]),
        )
        monkeypatch.setattr(
            mod.httpx, "AsyncClient", lambda **kw: _FakeGitHubAsyncClient(router, **kw)
        )

        connector = GitHubConnector(
            GitHubConfig(
                repos=["octo/hello"],
                token="ghp_x",
                include_pull_requests=True,
            )
        )
        docs = _run_github_pipeline(
            list(connector.reader.read_all_documents()), connector.converter
        )

        assert {d["id"] for d in docs} == {"octo/hello#1", "octo/hello#2"}
        kinds = {d["id"]: d["chunks"][0]["metadata"]["kind"] for d in docs}
        assert kinds["octo/hello#1"] == "issue"
        assert kinds["octo/hello#2"] == "pull_request"

    def test_output_structure(self, monkeypatch):
        """Converted output has correct keys and value types."""
        import indexed.connectors.github.github_graphql_reader as mod

        node = _github_issue_node(3, "Structure test", body="Some text")
        router = _make_github_router(issues_page=_github_issues_page([node]))
        monkeypatch.setattr(
            mod.httpx, "AsyncClient", lambda **kw: _FakeGitHubAsyncClient(router, **kw)
        )

        connector = GitHubConnector(GitHubConfig(repos=["octo/hello"], token="ghp_x"))
        docs = _run_github_pipeline(
            list(connector.reader.read_all_documents()), connector.converter
        )

        assert len(docs) == 1
        doc = docs[0]
        assert set(doc.keys()) == {"id", "url", "modifiedTime", "text", "chunks"}
        assert isinstance(doc["id"], str)
        assert isinstance(doc["url"], str)
        assert doc["url"].startswith("https://")
        assert isinstance(doc["modifiedTime"], str)
        assert isinstance(doc["text"], str)
        assert isinstance(doc["chunks"], list)
        assert len(doc["chunks"]) > 0
        for chunk in doc["chunks"]:
            assert "indexedData" in chunk
            assert isinstance(chunk["indexedData"], str)
