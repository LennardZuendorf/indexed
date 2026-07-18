"""Route registrars for the Jira Server / Confluence Server / Outline
localhost-stub E2E tests.

Each function wires ``pytest_httpserver.HTTPServer`` handlers that behave
like a real (small) server rather than an unconditional echo:

* **Auth-checked** -- every handler verifies the request's ``Authorization``
  header carries the expected bearer token before answering; a wrong or
  missing token gets a 401, not a free pass. Previously these routes
  ignored the header entirely, so a connector misconfigured with the wrong
  credential would still "index" successfully against the stub.
* **Offset-aware** -- the paged endpoints (Jira/Confluence search, Outline
  ``documents.list``) slice their backing item list by the request's
  offset/limit, capped at ``page_size`` per response. Previously these
  routes always echoed the same static first-page payload regardless of
  the requested offset, so a multi-page dataset would come back as
  duplicated first-page items instead of exercising real pagination.
* Outline's ``attachments.list`` / ``attachments.redirect`` and
  Confluence's default (``read_all_comments=True``) ``/child/comment``
  endpoint are registered here too, alongside the count+fetch endpoints,
  so those reader code paths are actually exercised by the E2E suite
  instead of being silently skipped.

No side effects at import time; nothing here talks to the network until a
caller registers routes on a live ``HTTPServer``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Request, Response

_COMMENT_PATH_RE = re.compile(r"^/rest/api/content/(?P<page_id>[^/]+)/child/comment$")
_FILE_PATH_RE = re.compile(r"^/files/(?P<att_id>[^/]+)$")


# --------------------------------------------------------------------------- #
# Shared helpers                                                              #
# --------------------------------------------------------------------------- #
def _bearer_unauthorized(request: Request, expected_token: str) -> Response | None:
    """Return a 401 ``Response`` when the request's bearer token is wrong or
    missing; ``None`` when it matches (auth OK -- caller proceeds).
    """
    if request.headers.get("Authorization") != f"Bearer {expected_token}":
        return Response(
            json.dumps({"message": "Unauthorized"}),
            status=401,
            content_type="application/json",
        )
    return None


def _json_response(payload: dict[str, Any]) -> Response:
    return Response(json.dumps(payload), content_type="application/json")


def _paginate(items: list[Any], offset: int, limit: int, page_size: int) -> list[Any]:
    """Slice ``items[offset : offset + n]`` with ``n`` capped at ``page_size``.

    Capping at ``page_size`` even when the caller's requested ``limit`` is
    larger is what makes this genuinely offset-aware: a caller must issue
    multiple requests to read more than one ``page_size``-sized window,
    mirroring a real server that caps its own page size, rather than a
    stub that would hand back everything (or the same first page) in one
    shot regardless of what the caller asked for.
    """
    n = max(0, min(limit, page_size))
    return items[offset : offset + n]


# --------------------------------------------------------------------------- #
# Jira Server                                                                 #
# --------------------------------------------------------------------------- #
def register_jira_server(
    httpserver: HTTPServer,
    *,
    issues: list[dict[str, Any]],
    expected_token: str,
    page_size: int = 500,
) -> None:
    """Register the Jira Server search endpoint.

    Serves ``GET /rest/api/2/search`` for both the document-count call
    (``maxResults=1``, reads ``total``) and paged fetch calls (reads
    ``issues``), slicing ``issues`` by ``startAt``/``maxResults`` (capped at
    ``page_size``). Rejects requests whose ``Authorization`` header isn't
    ``Bearer {expected_token}``.
    """

    def handler(request: Request) -> Response:
        unauthorized = _bearer_unauthorized(request, expected_token)
        if unauthorized is not None:
            return unauthorized
        start_at = int(request.args.get("startAt", 0))
        max_results = int(request.args.get("maxResults", page_size))
        page = _paginate(issues, start_at, max_results, page_size)
        return _json_response(
            {
                "issues": page,
                "total": len(issues),
                "startAt": start_at,
                "maxResults": max_results,
            }
        )

    httpserver.expect_request("/rest/api/2/search", method="GET").respond_with_handler(
        handler
    )


# --------------------------------------------------------------------------- #
# Confluence Server                                                          #
# --------------------------------------------------------------------------- #
def register_confluence_server(
    httpserver: HTTPServer,
    *,
    pages: list[dict[str, Any]],
    expected_token: str,
    comments_by_page_id: dict[str, list[dict[str, Any]]] | None = None,
    page_size: int = 500,
) -> None:
    """Register the Confluence Server content-search + comment endpoints.

    ``GET /rest/api/content/search`` serves both the document-count call
    (reads ``totalSize``) and paged fetch calls (reads ``results``), slicing
    ``pages`` by ``start``/``limit`` (capped at ``page_size``).

    ``GET /rest/api/content/{id}/child/comment`` is always registered too --
    it's only *hit* by the reader when ``read_all_comments=True`` (the
    default) and a page's ``children.comment.size`` is non-zero, per
    ``ConfluenceDocumentReader.__read_comments``. ``comments_by_page_id``
    supplies its payload per page id (offset-aware the same way); a page id
    absent from the mapping serves an empty result set.

    Both endpoints reject requests whose ``Authorization`` header isn't
    ``Bearer {expected_token}``.
    """
    comments_by_page_id = comments_by_page_id or {}

    def search_handler(request: Request) -> Response:
        unauthorized = _bearer_unauthorized(request, expected_token)
        if unauthorized is not None:
            return unauthorized
        start = int(request.args.get("start", 0))
        limit = int(request.args.get("limit", page_size))
        page = _paginate(pages, start, limit, page_size)
        return _json_response(
            {"results": page, "totalSize": len(pages), "start": start, "limit": limit}
        )

    httpserver.expect_request(
        "/rest/api/content/search", method="GET"
    ).respond_with_handler(search_handler)

    def comment_handler(request: Request) -> Response:
        unauthorized = _bearer_unauthorized(request, expected_token)
        if unauthorized is not None:
            return unauthorized
        match = _COMMENT_PATH_RE.match(request.path)
        page_id = match.group("page_id") if match else ""
        comments = comments_by_page_id.get(page_id, [])
        start = int(request.args.get("start", 0))
        limit = int(request.args.get("limit", page_size))
        page = _paginate(comments, start, limit, page_size)
        return _json_response(
            {"results": page, "size": len(comments), "start": start, "limit": limit}
        )

    httpserver.expect_request(_COMMENT_PATH_RE, method="GET").respond_with_handler(
        comment_handler
    )


# --------------------------------------------------------------------------- #
# Outline                                                                     #
# --------------------------------------------------------------------------- #
def register_outline(
    httpserver: HTTPServer,
    *,
    documents: list[dict[str, Any]],
    expected_token: str,
    page_size: int = 50,
    attachments_by_doc_id: dict[str, list[dict[str, Any]]] | None = None,
    attachment_bytes_by_id: dict[str, tuple[bytes, str]] | None = None,
) -> None:
    """Register the Outline documents (+ optional attachments) endpoints.

    ``POST /api/documents.list`` serves both the count call (reads
    ``pagination.total``) and paged fetch calls (reads ``data``), slicing
    ``documents`` by the request body's ``offset``/``limit`` (capped at
    ``page_size``). ``POST /api/documents.info`` looks up the full document
    by the requested ``id``.

    When ``attachments_by_doc_id`` is given, also registers
    ``POST /api/attachments.list`` (keyed by ``documentId``) and
    ``GET /api/attachments.redirect`` -- the latter issues a real 302 to a
    same-origin ``/files/<id>`` route serving bytes from
    ``attachment_bytes_by_id``, so the reader's redirect-follow download path
    is actually exercised rather than the final bytes being stubbed directly
    at the ``.redirect`` URL. Every endpoint above rejects requests whose
    ``Authorization`` header isn't ``Bearer {expected_token}``.
    """
    attachments_by_doc_id = attachments_by_doc_id or {}
    attachment_bytes_by_id = attachment_bytes_by_id or {}
    documents_by_id = {doc["id"]: doc for doc in documents}

    def list_handler(request: Request) -> Response:
        unauthorized = _bearer_unauthorized(request, expected_token)
        if unauthorized is not None:
            return unauthorized
        body = request.get_json(force=True) or {}
        offset = int(body.get("offset", 0))
        limit = int(body.get("limit", page_size))
        stubs = [{"id": doc["id"]} for doc in documents]
        page = _paginate(stubs, offset, limit, page_size)
        return _json_response(
            {
                "data": page,
                "pagination": {"offset": offset, "limit": limit, "total": len(stubs)},
            }
        )

    httpserver.expect_request(
        "/api/documents.list", method="POST"
    ).respond_with_handler(list_handler)

    def info_handler(request: Request) -> Response:
        unauthorized = _bearer_unauthorized(request, expected_token)
        if unauthorized is not None:
            return unauthorized
        body = request.get_json(force=True) or {}
        doc = documents_by_id.get(body.get("id"), {})
        return _json_response({"data": doc})

    httpserver.expect_request(
        "/api/documents.info", method="POST"
    ).respond_with_handler(info_handler)

    if not attachments_by_doc_id:
        return

    def attachments_list_handler(request: Request) -> Response:
        unauthorized = _bearer_unauthorized(request, expected_token)
        if unauthorized is not None:
            return unauthorized
        body = request.get_json(force=True) or {}
        atts = attachments_by_doc_id.get(body.get("documentId"), [])
        return _json_response({"data": atts})

    httpserver.expect_request(
        "/api/attachments.list", method="POST"
    ).respond_with_handler(attachments_list_handler)

    def redirect_handler(request: Request) -> Response:
        unauthorized = _bearer_unauthorized(request, expected_token)
        if unauthorized is not None:
            return unauthorized
        att_id = request.args.get("id", "")
        location = httpserver.url_for(f"/files/{att_id}")
        return Response(status=302, headers={"Location": location})

    httpserver.expect_request(
        "/api/attachments.redirect", method="GET"
    ).respond_with_handler(redirect_handler)

    # The redirect target: a same-origin URL serving the raw attachment
    # bytes, exactly as the real reader (follow_redirects=True) expects.
    # Deliberately unauthenticated -- mirrors a real Outline server, which
    # redirects to a pre-signed, credential-less storage URL.
    def file_handler(request: Request) -> Response:
        match = _FILE_PATH_RE.match(request.path)
        att_id = match.group("att_id") if match else ""
        data, mime = attachment_bytes_by_id.get(
            att_id, (b"", "application/octet-stream")
        )
        return Response(data, content_type=mime)

    httpserver.expect_request(_FILE_PATH_RE, method="GET").respond_with_handler(
        file_handler
    )
