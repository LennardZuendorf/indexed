"""Route registrars for the Jira Server / Confluence Server / Outline
localhost-stub E2E tests.

Each function wires permanent, unordered handlers onto a
``pytest_httpserver.HTTPServer`` instance so that both the "count" call
(``limit=1`` / ``maxResults=1``) and the subsequent "fetch" call made by the
real connector readers are served from the same JSON payload. Query string
and request body are intentionally left unmatched (path + method only) so a
single handler answers every request variant a connector makes during one
E2E happy-path run.

No side effects at import time; nothing here talks to the network until a
caller registers routes on a live ``HTTPServer``.
"""

from __future__ import annotations

from typing import Any

from pytest_httpserver import HTTPServer


def register_jira_server(
    httpserver: HTTPServer,
    *,
    search_payload: dict[str, Any],
) -> None:
    """Register the Jira Server search endpoint.

    Serves ``GET /rest/api/2/search`` for both the document-count call
    (``maxResults=1``, reads ``total``) and the fetch call (reads
    ``issues``).
    """
    httpserver.expect_request(
        "/rest/api/2/search",
        method="GET",
    ).respond_with_json(search_payload)


def register_confluence_server(
    httpserver: HTTPServer,
    *,
    search_payload: dict[str, Any],
) -> None:
    """Register the Confluence Server content-search endpoint.

    Serves ``GET /rest/api/content/search`` for both the document-count
    call (reads ``totalSize``) and the fetch call (reads ``results``).
    """
    httpserver.expect_request(
        "/rest/api/content/search",
        method="GET",
    ).respond_with_json(search_payload)


def register_outline(
    httpserver: HTTPServer,
    *,
    documents_list: dict[str, Any],
    document_info: dict[str, Any],
) -> None:
    """Register the Outline documents endpoints.

    Serves ``POST /api/documents.list`` (reads ``pagination.total`` +
    ``data``) and ``POST /api/documents.info`` (reads ``data``).
    ``attachments.list`` / ``collections.list`` are intentionally not
    registered here -- the happy path skips them via
    ``--no-include-attachments`` and an explicit ``--collection-id``.
    """
    httpserver.expect_request(
        "/api/documents.list",
        method="POST",
    ).respond_with_json(documents_list)
    httpserver.expect_request(
        "/api/documents.info",
        method="POST",
    ).respond_with_json(document_info)
