"""Fixture payload builders for Jira Server, Confluence Server, and Outline E2E tests.

These builders return realistic API item dicts for use with the offset-aware,
auth-checked ``pytest_httpserver`` stubs in ``stub_routes.py``. Each includes a
seeded phrase for search validation (via index search). Callers hand a *list*
of these items straight to the matching ``stub_routes.register_*`` function --
pagination envelopes (``total``/``pagination``/``size`` etc.) are built by the
stub itself from the list length and the request's offset, not baked in here.
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

    Default includes seeded phrase: "database timeout on staging".
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


def confluence_server_page(
    page_id: str = "101",
    title: str = "Setup Guide",
    body_html: str | None = None,
    updated: str = "2026-01-15T10:00:00.000Z",
    base_url: str = "http://localhost",
    webui: str = "/display/DOCS/Setup+Guide",
    comment_count: int = 0,
) -> dict[str, Any]:
    """Build a realistic Confluence Server page dict.

    Default includes seeded phrase: "Install the package with pip".
    ``comment_count`` sets ``children.comment.size`` -- 0 (the default) means
    neither comment-read mode issues a further request; a non-zero count is
    what makes the reader's default ``read_all_comments=True`` path fetch
    comments via the separate ``/child/comment`` endpoint that
    ``stub_routes.register_confluence_server`` serves from its
    ``comments_by_page_id`` argument.
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
                "size": comment_count,
                "results": [],
            }
        },
    }


def confluence_comment(body_html: str) -> dict[str, Any]:
    """Build a Confluence comment dict as returned by the ``/child/comment`` endpoint."""
    return {"body": {"storage": {"value": body_html}}}


def outline_document_info(
    doc_id: str = "d1",
    title: str = "Runbook: Deploying the API",
    text: str | None = None,
    url: str | None = None,
    updated_at: str = "2026-01-01T00:00:00Z",
    collection_id: str = "col1",
) -> dict[str, Any]:
    """Build an Outline document dict (the ``documents.info`` "data" shape).

    Default includes seeded phrase: "rotate the vault token".
    """
    if text is None:
        text = "To deploy the API you must rotate the vault token first."
    if url is None:
        url = f"https://app.getoutline.com/doc/{doc_id}"

    return {
        "id": doc_id,
        "title": title,
        "text": text,
        "url": url,
        "updatedAt": updated_at,
        "collectionId": collection_id,
        "parentDocumentId": None,
    }


def outline_attachment_stub(
    att_id: str = "att1", name: str = "notes.txt"
) -> dict[str, Any]:
    """Build an Outline attachment listing entry (the ``attachments.list`` "data" shape)."""
    return {"id": att_id, "name": name}
