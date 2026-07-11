"""Fixture payload builders for Jira Server, Confluence Server, and Outline E2E tests.

These builders return realistic API response dicts for use with pytest-httpserver stubs.
Each includes a seeded phrase for search validation (via index search).
"""

from __future__ import annotations

from typing import Any


def jira_server_issue(
    key: str = "SRV-1",
    summary: str = "Login page returns 500 error",
    description: str | None = None,
    comments: list[dict[str, Any]] | None = None,
    updated: str = "2026-01-15T10:00:00.000+0000",
    base_url: str = "http://localhost",
) -> dict[str, Any]:
    """Build a realistic Jira Server issue dict.

    Includes seeded phrase: "database timeout on staging".
    """
    if description is None:
        description = (
            "Users hitting the checkout flow see a database timeout on staging."
        )
    if comments is None:
        comments = [{"body": "Fixed by bumping the connection pool size."}]

    return {
        "key": key,
        "self": f"{base_url}/rest/api/2/issue/{key.split('-')[-1]}",
        "fields": {
            "summary": summary,
            "updated": updated,
            "description": description,
            "comment": {"comments": comments},
        },
    }


def jira_server_search(
    issue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Jira Server search response wrapping one issue.

    Serves both count (reads 'total') and fetch (reads 'issues') calls.
    """
    if issue is None:
        issue = jira_server_issue()
    return {
        "issues": [issue],
        "total": 1,
        "startAt": 0,
        "maxResults": 1,
    }


def confluence_server_page(
    page_id: str = "101",
    title: str = "Setup Guide",
    body_html: str | None = None,
    updated: str = "2026-01-15T10:00:00.000Z",
    base_url: str = "http://localhost",
    webui: str = "/display/DOCS/Setup+Guide",
) -> dict[str, Any]:
    """Build a realistic Confluence Server page dict.

    Includes seeded phrase: "Install the package with pip".
    Comment size set to 0 (no comment fetching on happy path).
    """
    if body_html is None:
        body_html = "<h2>Getting Started</h2><p>Install the package with pip.</p>"

    return {
        "id": page_id,
        "title": title,
        "ancestors": [{"title": "Documentation"}],
        "body": {"storage": {"value": body_html}},
        "version": {"when": updated},
        "_links": {
            "self": f"{base_url}/rest/api/content/{page_id}",
            "webui": webui,
        },
        "children": {
            "comment": {
                "size": 0,
                "results": [],
            }
        },
    }


def confluence_server_search(
    page: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a Confluence Server search response wrapping one page.

    Serves both count (reads 'totalSize') and fetch (reads 'results') calls.
    """
    if page is None:
        page = confluence_server_page()
    return {
        "results": [page],
        "totalSize": 1,
    }


def outline_doc_stub(
    doc_id: str = "d1",
) -> dict[str, Any]:
    """Build a minimal Outline document stub for documents.list response."""
    return {"id": doc_id}


def outline_documents_list(
    stub: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an Outline documents.list response wrapping one document.

    Serves both count (reads 'pagination.total') and list (reads 'data') calls.
    """
    if stub is None:
        stub = outline_doc_stub()
    return {
        "data": [stub],
        "pagination": {
            "offset": 0,
            "limit": 1,
            "total": 1,
        },
    }


def outline_document_info(
    doc_id: str = "d1",
    title: str = "Runbook: Deploying the API",
    text: str | None = None,
    url: str | None = None,
    updated_at: str = "2026-01-01T00:00:00Z",
    collection_id: str = "col1",
) -> dict[str, Any]:
    """Build an Outline documents.info response for a single document.

    Includes seeded phrase: "rotate the vault token".
    """
    if text is None:
        text = "To deploy the API you must rotate the vault token first."
    if url is None:
        url = f"https://app.getoutline.com/doc/{doc_id}"

    return {
        "data": {
            "id": doc_id,
            "title": title,
            "text": text,
            "url": url,
            "updatedAt": updated_at,
            "collectionId": collection_id,
            "parentDocumentId": None,
        }
    }
