"""End-to-end mocked integration tests for OutlineDocumentReader.

Exercises read_all_documents() with httpx.AsyncClient and requests.post mocked,
so the full sequence collections.list → documents.list → documents.info →
attachments.list → attachments.redirect runs through the real orchestration code.
"""

from __future__ import annotations

from typing import Callable
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


class _FakeResp:
    """Stand-in for both requests.Response and httpx.Response."""

    def __init__(
        self,
        status: int = 200,
        payload: dict | None = None,
        content: bytes = b"",
        headers: dict | None = None,
    ) -> None:
        self.status_code = status
        self._payload = payload or {}
        self.content = content
        self.headers = headers or {}
        self.text = ""
        self.url = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Async context manager that routes requests via a callable."""

    def __init__(self, router: Callable[[str, str], _FakeResp]) -> None:
        self._router = router

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> _FakeResp:
        return self._router("POST", url)

    async def get(self, url: str, **kwargs: object) -> _FakeResp:
        return self._router("GET", url)


def _doc_list(docs: list[dict], total: int, offset: int = 0) -> _FakeResp:
    return _FakeResp(
        payload={
            "data": docs,
            "pagination": {"offset": offset, "limit": len(docs), "total": total},
        }
    )


def _doc_info(doc_id: str, text: str = "") -> _FakeResp:
    return _FakeResp(
        payload={
            "data": {
                "id": doc_id,
                "title": f"Doc {doc_id}",
                "text": text,
                "url": f"https://app.getoutline.com/doc/{doc_id}",
                "updatedAt": "2026-01-01T00:00:00Z",
                "collectionId": "col1",
                "parentDocumentId": None,
            }
        }
    )


def _collections(ids: list[str]) -> _FakeResp:
    return _FakeResp(
        payload={
            "data": [{"id": cid} for cid in ids],
            "pagination": {"offset": 0, "limit": len(ids), "total": len(ids)},
        }
    )


def _attachments_list(items: list[dict]) -> _FakeResp:
    return _FakeResp(
        payload={
            "data": items,
            "pagination": {"offset": 0, "limit": len(items), "total": len(items)},
        }
    )


def _attachment_bytes(data: bytes, mime: str = "image/png") -> _FakeResp:
    return _FakeResp(
        content=data,
        headers={"content-length": str(len(data)), "content-type": mime},
    )


# ---------------------------------------------------------------------------
# Reader factory
# ---------------------------------------------------------------------------


def _make_reader(**overrides):
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    kwargs: dict = dict(
        base_url="https://app.getoutline.com",
        api_token="ol_api_test",
        collection_ids=["col1"],
        batch_size=10,
        max_concurrent_requests=4,
        include_attachments=True,
        download_inline_images=True,
        max_attachment_size_mb=10,
        number_of_retries=3,
        retry_delay=0.0,
    )
    kwargs.update(overrides)
    return OutlineDocumentReader(**kwargs)


def _patch_async_client(router: Callable[[str, str], _FakeResp]):
    """Patch httpx.AsyncClient inside the reader module to use our fake."""
    return patch(
        "connectors.outline.outline_document_reader.httpx.AsyncClient",
        new=lambda **kw: _FakeAsyncClient(router),
    )


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


def test_full_pipeline_yields_documents_with_attachments() -> None:
    """One collection, two docs, each with one listed attachment — full envelope."""
    reader = _make_reader()

    sync_calls = [
        _doc_list([{"id": "d1"}, {"id": "d2"}], total=2),
    ]

    def router(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            # Determine which doc by tracking call count
            doc_id = "d1" if router.info_calls == 0 else "d2"
            router.info_calls += 1
            return _doc_info(doc_id, text="Body content.")
        if "attachments.list" in url:
            router.list_calls += 1
            return _attachments_list(
                [{"id": f"att{router.list_calls}", "name": "diagram.png"}]
            )
        if "attachments.redirect" in url:
            return _attachment_bytes(b"PNGDATA")
        raise AssertionError(f"unexpected {method} {url}")

    router.info_calls = 0
    router.list_calls = 0

    with patch("requests.post", side_effect=sync_calls), _patch_async_client(router):
        envelopes = list(reader.read_all_documents())

    assert len(envelopes) == 2
    ids = sorted(e["document"]["id"] for e in envelopes)
    assert ids == ["d1", "d2"]
    for env in envelopes:
        assert len(env["attachments"]) == 1
        assert env["attachments"][0]["bytes"] == b"PNGDATA"
        assert env["attachments"][0]["mimeType"] == "image/png"


def test_inline_image_deduped_with_listed_attachment() -> None:
    """Same attachment id in attachments.list AND inline Markdown → downloaded once."""
    reader = _make_reader()
    inline_md = "![](https://app.getoutline.com/api/attachments.redirect?id=shared-att)"

    sync_calls = [_doc_list([{"id": "d1"}], total=1)]

    download_count = {"n": 0}

    def router(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            return _doc_info("d1", text=f"Pre {inline_md} post.")
        if "attachments.list" in url:
            return _attachments_list([{"id": "shared-att", "name": "shared.png"}])
        if "attachments.redirect" in url:
            download_count["n"] += 1
            return _attachment_bytes(b"PIXELS")
        raise AssertionError(url)

    with patch("requests.post", side_effect=sync_calls), _patch_async_client(router):
        envelopes = list(reader.read_all_documents())

    assert download_count["n"] == 1
    assert len(envelopes[0]["attachments"]) == 1
    assert envelopes[0]["attachments"][0]["id"] == "shared-att"


# ---------------------------------------------------------------------------
# Retry & failure paths
# ---------------------------------------------------------------------------


def test_body_fetch_retries_on_failure_then_succeeds() -> None:
    """documents.info fails twice (transient), succeeds on third attempt."""
    reader = _make_reader()
    attempts = {"n": 0}

    def router(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("transient")
            return _doc_info("d1")
        if "attachments.list" in url:
            return _attachments_list([])
        raise AssertionError(url)

    sync_calls = [_doc_list([{"id": "d1"}], total=1)]

    with patch("requests.post", side_effect=sync_calls), _patch_async_client(router):
        envelopes = list(reader.read_all_documents())

    assert attempts["n"] == 3
    assert len(envelopes) == 1
    assert envelopes[0]["document"]["id"] == "d1"


def test_body_fetch_all_retries_fail_doc_skipped() -> None:
    """When documents.info exhausts retries, the doc is dropped from output."""
    reader = _make_reader(number_of_retries=2)

    def router(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            raise RuntimeError("permanent")
        if "attachments.list" in url:
            return _attachments_list([])
        raise AssertionError(url)

    sync_calls = [_doc_list([{"id": "d1"}, {"id": "d2"}], total=2)]

    def router_with_one_success(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            router_with_one_success.calls += 1
            # First doc succeeds, second always fails
            if router_with_one_success.calls == 1:
                return _doc_info("d1")
            raise RuntimeError("permanent")
        if "attachments.list" in url:
            return _attachments_list([])
        raise AssertionError(url)

    router_with_one_success.calls = 0

    with (
        patch("requests.post", side_effect=sync_calls),
        _patch_async_client(router_with_one_success),
    ):
        envelopes = list(reader.read_all_documents())

    # Only the doc that succeeded is yielded
    yielded_ids = [e["document"]["id"] for e in envelopes]
    assert "d1" in yielded_ids
    assert "d2" not in yielded_ids


def test_attachments_fetch_exception_yields_empty_list() -> None:
    """If attachments task raises, the doc is still yielded with [] attachments."""
    reader = _make_reader()

    def router(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            return _doc_info("d1")
        if "attachments.list" in url:
            # Simulate a non-network error escaping the inner try/except
            raise KeyboardInterrupt("forced")
        raise AssertionError(url)

    sync_calls = [_doc_list([{"id": "d1"}], total=1)]

    with patch("requests.post", side_effect=sync_calls), _patch_async_client(router):
        # KeyboardInterrupt is not caught by the inner try; it bubbles up to
        # asyncio.gather(return_exceptions=True). Use a regular Exception subclass.
        pass

    # Replace KeyboardInterrupt with a regular Exception (gather catches those)
    def safer_router(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            return _doc_info("d1")
        if "attachments.list" in url:
            raise RuntimeError("inner failure")
        raise AssertionError(url)

    sync_calls = [_doc_list([{"id": "d1"}], total=1)]

    with (
        patch("requests.post", side_effect=sync_calls),
        _patch_async_client(safer_router),
    ):
        envelopes = list(reader.read_all_documents())

    # _list_attachments swallows the exception and returns [] internally
    assert len(envelopes) == 1
    assert envelopes[0]["attachments"] == []


# ---------------------------------------------------------------------------
# OutlineAPIError on 4xx
# ---------------------------------------------------------------------------


def test_outline_api_error_raised_on_4xx_listing() -> None:
    """documents.list returning 401 → OutlineAPIError propagates."""
    from connectors.outline.outline_document_reader import OutlineAPIError

    reader = _make_reader()

    err_resp = MagicMock()
    err_resp.status_code = 401
    err_resp.json.return_value = {"message": "unauthorized"}
    err_resp.text = '{"message":"unauthorized"}'
    err_resp.url = "https://app.getoutline.com/api/documents.list"

    with patch("requests.post", return_value=err_resp):
        with pytest.raises(OutlineAPIError) as exc:
            list(reader._iter_document_stubs())

    assert exc.value.status_code == 401
    assert "unauthorized" in str(exc.value)


def test_outline_api_error_falls_back_to_text_when_json_invalid() -> None:
    """_raise_for_status uses resp.text when json() raises."""
    from connectors.outline.outline_document_reader import (
        OutlineAPIError,
        OutlineDocumentReader,
    )

    err_resp = MagicMock()
    err_resp.status_code = 500
    err_resp.json.side_effect = ValueError("not json")
    err_resp.text = "Internal Server Error"
    err_resp.url = "https://x/y"

    with pytest.raises(OutlineAPIError) as exc:
        OutlineDocumentReader._raise_for_status(err_resp)

    assert exc.value.status_code == 500
    assert "Internal Server Error" in str(exc.value)


def test_documents_list_retries_on_transient_then_succeeds() -> None:
    """documents.list raises ConnectionError twice, succeeds on third."""
    reader = _make_reader(number_of_retries=3)

    err = ConnectionError("transient")
    success = _doc_list([{"id": "d1"}], total=1)

    with (
        patch("requests.post", side_effect=[err, err, success]),
        patch(
            "connectors.outline.outline_document_reader.httpx.AsyncClient",
            new=lambda **kw: _FakeAsyncClient(
                lambda m, u: (
                    _doc_info("d1") if "documents.info" in u else _attachments_list([])
                )
            ),
        ),
    ):
        envelopes = list(reader.read_all_documents())

    assert len(envelopes) == 1
    assert envelopes[0]["document"]["id"] == "d1"


# ---------------------------------------------------------------------------
# get_number_of_documents
# ---------------------------------------------------------------------------


def test_get_number_of_documents_sums_per_collection() -> None:
    """One probe per collection; totals summed across collections."""
    reader = _make_reader(collection_ids=["c1", "c2"])

    responses = [
        _doc_list([], total=12),
        _doc_list([], total=7),
    ]

    with patch("requests.post", side_effect=responses) as mock_post:
        total = reader.get_number_of_documents()

    assert total == 19
    assert mock_post.call_count == 2


def test_get_number_of_documents_with_no_collections_returns_zero() -> None:
    """Auto-fetched empty collection list → zero docs."""
    reader = _make_reader(collection_ids=None)

    empty_collections = _collections([])

    with patch("requests.post", return_value=empty_collections):
        total = reader.get_number_of_documents()

    assert total == 0


# ---------------------------------------------------------------------------
# Inline image-only path (download_inline_images without include_attachments)
# ---------------------------------------------------------------------------


def test_inline_image_only_when_attachments_disabled() -> None:
    """include_attachments=False but download_inline_images=True still pulls inline imgs."""
    reader = _make_reader(include_attachments=False, download_inline_images=True)
    inline_md = "![](https://app.getoutline.com/api/attachments.redirect?id=inline-1)"

    sync_calls = [_doc_list([{"id": "d1"}], total=1)]

    listed = {"n": 0}

    def router(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            return _doc_info("d1", text=f"Inline: {inline_md}")
        if "attachments.list" in url:
            listed["n"] += 1
            return _attachments_list([])
        if "attachments.redirect" in url:
            return _attachment_bytes(b"INLINEPIXELS")
        raise AssertionError(url)

    with patch("requests.post", side_effect=sync_calls), _patch_async_client(router):
        envelopes = list(reader.read_all_documents())

    # attachments.list should NOT be called when include_attachments=False
    assert listed["n"] == 0
    # But the inline image should still be downloaded
    assert len(envelopes[0]["attachments"]) == 1
    assert envelopes[0]["attachments"][0]["id"] == "inline-1"


def test_no_attachment_fetching_when_both_disabled() -> None:
    """Both flags off: no attachment HTTP calls of any kind."""
    reader = _make_reader(include_attachments=False, download_inline_images=False)

    sync_calls = [_doc_list([{"id": "d1"}], total=1)]

    def router(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            return _doc_info("d1", text="just text")
        # If any attachment endpoint is hit, fail loudly
        raise AssertionError(f"should not call {url}")

    with patch("requests.post", side_effect=sync_calls), _patch_async_client(router):
        envelopes = list(reader.read_all_documents())

    assert len(envelopes) == 1
    assert envelopes[0]["attachments"] == []


# ---------------------------------------------------------------------------
# _yield_window — explicit windowing test
# ---------------------------------------------------------------------------


def test_yield_window_skips_failed_doc_bodies() -> None:
    """_yield_window drops entries where _fetch_body returned None."""
    reader = _make_reader(number_of_retries=1)

    def router(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            router.calls += 1
            if router.calls == 1:
                return _doc_info("ok")
            raise RuntimeError("dead")
        if "attachments.list" in url:
            return _attachments_list([])
        raise AssertionError(url)

    router.calls = 0

    with _patch_async_client(router):
        results = list(reader._yield_window([{"id": "ok"}, {"id": "broken"}]))

    assert len(results) == 1
    assert results[0]["document"]["id"] == "ok"


def test_yield_window_with_attachment_disabled_skips_attachment_phase() -> None:
    """_yield_window with both attachment flags off skips the attachments async call."""
    reader = _make_reader(include_attachments=False, download_inline_images=False)

    def router(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            return _doc_info("d1")
        raise AssertionError(f"should not call {url}")

    with _patch_async_client(router):
        results = list(reader._yield_window([{"id": "d1"}]))

    assert len(results) == 1
    assert results[0]["attachments"] == []


# ---------------------------------------------------------------------------
# Pagination across multiple pages (full pipeline)
# ---------------------------------------------------------------------------


def test_full_pipeline_paginates_documents_list() -> None:
    """documents.list returns 3 pages; all docs flow through pipeline."""
    reader = _make_reader(batch_size=2)

    sync_calls = [
        _doc_list([{"id": "d1"}, {"id": "d2"}], total=5, offset=0),
        _doc_list([{"id": "d3"}, {"id": "d4"}], total=5, offset=2),
        _doc_list([{"id": "d5"}], total=5, offset=4),
    ]

    def router(method: str, url: str) -> _FakeResp:
        if "documents.info" in url:
            return _doc_info("dx")  # body content irrelevant for this test
        if "attachments.list" in url:
            return _attachments_list([])
        raise AssertionError(url)

    with (
        patch("requests.post", side_effect=sync_calls) as mock_post,
        _patch_async_client(router),
    ):
        envelopes = list(reader.read_all_documents())

    assert len(envelopes) == 5
    assert mock_post.call_count == 3
