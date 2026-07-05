"""Tests for OutlineDocumentReader pagination and collection resolution."""

import pytest
from unittest.mock import MagicMock, patch


def _make_doc_list_response(docs: list, total: int, offset: int = 0) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": docs,
        "pagination": {"offset": offset, "limit": len(docs), "total": total},
    }
    return resp


def _make_collections_response(ids: list[str]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": [{"id": cid} for cid in ids],
        "pagination": {"offset": 0, "limit": len(ids), "total": len(ids)},
    }
    return resp


def _make_doc_info_response(doc_id: str) -> dict:
    return {
        "data": {
            "id": doc_id,
            "title": f"Doc {doc_id}",
            "text": f"# {doc_id}\n\nContent here.",
            "url": f"https://app.getoutline.com/doc/{doc_id}",
            "updatedAt": "2026-01-01T00:00:00Z",
            "collectionId": "col1",
            "parentDocumentId": None,
        }
    }


@pytest.fixture
def reader():
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    return OutlineDocumentReader(
        base_url="https://app.getoutline.com",
        api_token="ol_api_test",
        collection_ids=["col1"],
        batch_size=2,
        max_concurrent_requests=2,
        include_attachments=False,
        download_inline_images=False,
    )


@pytest.mark.unit
@pytest.mark.api
def test_pagination_terminates_at_total(reader) -> None:
    doc_stubs = [{"id": f"doc{i}"} for i in range(5)]

    responses = [
        _make_doc_list_response(doc_stubs[:2], total=5, offset=0),
        _make_doc_list_response(doc_stubs[2:4], total=5, offset=2),
        _make_doc_list_response(doc_stubs[4:], total=5, offset=4),
    ]

    with patch("requests.post", side_effect=responses) as mock_post:
        stubs = list(reader._iter_document_stubs())

    assert len(stubs) == 5
    assert mock_post.call_count == 3


@pytest.mark.unit
@pytest.mark.api
def test_pagination_with_exact_page_boundary(reader) -> None:
    doc_stubs = [{"id": f"doc{i}"} for i in range(4)]

    responses = [
        _make_doc_list_response(doc_stubs[:2], total=4, offset=0),
        _make_doc_list_response(doc_stubs[2:], total=4, offset=2),
    ]

    with patch("requests.post", side_effect=responses):
        stubs = list(reader._iter_document_stubs())

    assert len(stubs) == 4


@pytest.mark.unit
@pytest.mark.api
def test_empty_collection(reader) -> None:
    with patch("requests.post", return_value=_make_doc_list_response([], total=0)):
        stubs = list(reader._iter_document_stubs())
    assert stubs == []


@pytest.mark.unit
@pytest.mark.api
def test_collection_ids_none_fetches_collections() -> None:
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    r = OutlineDocumentReader(
        base_url="https://app.getoutline.com",
        api_token="tok",
        collection_ids=None,
        include_attachments=False,
        download_inline_images=False,
    )

    collections_resp = _make_collections_response(["col1", "col2"])
    docs_resp = _make_doc_list_response([], total=0)

    with patch("requests.post", side_effect=[collections_resp, docs_resp, docs_resp]):
        ids = r._get_collection_ids_sync()

    assert ids == ["col1", "col2"]


@pytest.mark.unit
@pytest.mark.api
def test_collection_ids_provided_skips_collections_call(reader) -> None:
    assert reader.collection_ids == ["col1"]

    docs_resp = _make_doc_list_response([], total=0)
    with patch("requests.post", return_value=docs_resp) as mock_post:
        reader._get_collection_ids_sync()

    # Should not call collections.list
    for c in mock_post.call_args_list:
        assert "collections.list" not in str(c)


@pytest.mark.unit
def test_reader_details(reader) -> None:
    details = reader.get_reader_details()
    assert details["type"] == "outline"
    assert details["baseUrl"] == "https://app.getoutline.com"
    assert details["ocrEnabled"] is True


@pytest.mark.unit
def test_extract_attachment_id() -> None:
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    url = "https://app.getoutline.com/api/attachments.redirect?id=abc-123&sig=xyz"
    assert OutlineDocumentReader._extract_attachment_id(url) == "abc-123"


@pytest.mark.unit
def test_extract_attachment_id_missing() -> None:
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    assert (
        OutlineDocumentReader._extract_attachment_id("https://example.com/no-id") == ""
    )


@pytest.mark.unit
def test_ext_from_url_png() -> None:
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    assert (
        OutlineDocumentReader._ext_from_url(
            "https://host/api/attachments.redirect?id=x"
        )
        == ".png"
    )


@pytest.mark.unit
def test_ext_from_url_pdf() -> None:
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    assert OutlineDocumentReader._ext_from_url("https://host/files/doc.pdf") == ".pdf"


@pytest.mark.unit
def test_documents_list_payload_includes_sort(reader) -> None:
    payload = reader._documents_list_payload("col1", offset=0)
    assert payload["sort"] == "updatedAt"
    assert payload["direction"] == "DESC"
    assert payload["collectionId"] == "col1"
    assert payload["status"] == "published"


@pytest.mark.unit
def test_incremental_update_yields_only_newer_docs(reader) -> None:
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    incremental = OutlineDocumentReader(
        base_url="https://app.getoutline.com",
        api_token="ol_api_test",
        collection_ids=["col1"],
        batch_size=10,
        include_attachments=False,
        download_inline_images=False,
        modified_since="2026-03-15T10:00:00+00:00",
    )

    doc_stubs = [
        {"id": "doc-new", "updatedAt": "2026-03-16T10:00:00Z"},
        {"id": "doc-boundary", "updatedAt": "2026-03-15T10:00:00Z"},
        {"id": "doc-old", "updatedAt": "2026-03-14T10:00:00Z"},
    ]
    responses = [_make_doc_list_response(doc_stubs, total=3)]

    with patch("requests.post", side_effect=responses) as mock_post:
        stubs = list(incremental._iter_document_stubs())

    assert [stub["id"] for stub in stubs] == ["doc-new", "doc-boundary"]
    assert mock_post.call_count == 1
    payload = mock_post.call_args.kwargs["json"]
    assert payload["sort"] == "updatedAt"
    assert payload["direction"] == "DESC"


@pytest.mark.unit
def test_incremental_update_stops_paging_at_first_older_doc(reader) -> None:
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    incremental = OutlineDocumentReader(
        base_url="https://app.getoutline.com",
        api_token="ol_api_test",
        collection_ids=["col1"],
        batch_size=2,
        include_attachments=False,
        download_inline_images=False,
        modified_since="2026-03-15T10:00:00+00:00",
    )

    page_one = [
        {"id": "doc-new", "updatedAt": "2026-03-16T10:00:00Z"},
        {"id": "doc-old", "updatedAt": "2026-03-14T10:00:00Z"},
    ]
    page_two = [{"id": "doc-older", "updatedAt": "2026-03-10T10:00:00Z"}]
    responses = [
        _make_doc_list_response(page_one, total=3, offset=0),
        _make_doc_list_response(page_two, total=3, offset=2),
    ]

    with patch("requests.post", side_effect=responses) as mock_post:
        stubs = list(incremental._iter_document_stubs())

    assert [stub["id"] for stub in stubs] == ["doc-new"]
    assert mock_post.call_count == 1


@pytest.mark.unit
def test_no_modified_since_yields_all_docs(reader) -> None:
    doc_stubs = [
        {"id": "doc-new", "updatedAt": "2026-03-16T10:00:00Z"},
        {"id": "doc-old", "updatedAt": "2026-03-14T10:00:00Z"},
    ]
    responses = [_make_doc_list_response(doc_stubs, total=2)]

    with patch("requests.post", side_effect=responses):
        stubs = list(reader._iter_document_stubs())

    assert len(stubs) == 2


@pytest.mark.unit
def test_incremental_update_includes_stubs_missing_updated_at() -> None:
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    incremental = OutlineDocumentReader(
        base_url="https://app.getoutline.com",
        api_token="ol_api_test",
        collection_ids=["col1"],
        batch_size=10,
        include_attachments=False,
        download_inline_images=False,
        modified_since="2026-03-15T10:00:00+00:00",
    )

    doc_stubs = [
        {"id": "doc-new", "updatedAt": "2026-03-16T10:00:00Z"},
        {"id": "doc-no-timestamp"},
        {"id": "doc-old", "updatedAt": "2026-03-14T10:00:00Z"},
    ]
    responses = [_make_doc_list_response(doc_stubs, total=3)]

    with patch("requests.post", side_effect=responses):
        stubs = list(incremental._iter_document_stubs())

    assert [stub["id"] for stub in stubs] == ["doc-new", "doc-no-timestamp"]


@pytest.mark.unit
def test_insecure_tls_logs_warning() -> None:
    from connectors.outline.outline_document_reader import OutlineDocumentReader
    from unittest.mock import patch

    with patch("connectors.outline.outline_document_reader.logger") as mock_logger:
        OutlineDocumentReader(
            base_url="https://app.getoutline.com",
            api_token="tok",
            verify_ssl=False,
        )

    mock_logger.warning.assert_called_once()
    warning_message = mock_logger.warning.call_args[0][0]
    assert "TLS certificate verification is DISABLED" in warning_message


@pytest.mark.unit
def test_secure_tls_no_warning() -> None:
    from connectors.outline.outline_document_reader import OutlineDocumentReader
    from unittest.mock import patch

    with patch("connectors.outline.outline_document_reader.logger") as mock_logger:
        OutlineDocumentReader(
            base_url="https://app.getoutline.com",
            api_token="tok",
        )

    for call in mock_logger.warning.call_args_list:
        assert "TLS" not in str(call)


@pytest.mark.unit
def test_get_number_of_documents_uses_stub_count_when_incremental() -> None:
    from connectors.outline.outline_document_reader import OutlineDocumentReader

    incremental = OutlineDocumentReader(
        base_url="https://app.getoutline.com",
        api_token="ol_api_test",
        collection_ids=["col1"],
        batch_size=10,
        include_attachments=False,
        download_inline_images=False,
        modified_since="2026-03-15T10:00:00+00:00",
    )

    doc_stubs = [
        {"id": "doc-new", "updatedAt": "2026-03-16T10:00:00Z"},
        {"id": "doc-old", "updatedAt": "2026-03-14T10:00:00Z"},
    ]

    with patch(
        "requests.post", return_value=_make_doc_list_response(doc_stubs, total=2)
    ):
        count = incremental.get_number_of_documents()

    assert count == 1
