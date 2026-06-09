"""Tests for OutlineDocumentConverter chunk emission, title path, and attachment parsing."""

import base64
import pytest
from unittest.mock import MagicMock


def _make_document(
    doc_id: str = "doc1",
    title: str = "My Document",
    text: str = "# My Document\n\nSome content.",
    url: str = "https://app.getoutline.com/doc/my-document",
    updated_at: str = "2026-01-01T00:00:00Z",
    parent_id: str | None = None,
    attachments: list | None = None,
) -> dict:
    return {
        "document": {
            "id": doc_id,
            "title": title,
            "text": text,
            "url": url,
            "updatedAt": updated_at,
            "parentDocumentId": parent_id,
        },
        "attachments": attachments or [],
    }


@pytest.fixture
def converter():
    from connectors.outline.outline_document_converter import OutlineDocumentConverter

    return OutlineDocumentConverter(
        max_chunk_tokens=512, ocr=False, include_attachments=True
    )


@pytest.fixture
def mock_parser():
    chunk = MagicMock()
    chunk.contextualized_text = "mocked chunk text"
    chunk.metadata = {"section": "intro"}

    parsed = MagicMock()
    parsed.chunks = [chunk]

    parser = MagicMock()
    parser.parse_bytes.return_value = parsed
    return parser


@pytest.mark.unit
def test_convert_returns_list_with_one_entry(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document()
    result = list(converter.convert(doc))
    assert len(result) == 1


@pytest.mark.unit
def test_convert_preserves_id(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(doc_id="abc-123")
    result = list(converter.convert(doc))
    assert result[0]["id"] == "abc-123"


@pytest.mark.unit
def test_convert_preserves_url(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(url="https://app.getoutline.com/doc/test")
    result = list(converter.convert(doc))
    assert result[0]["url"] == "https://app.getoutline.com/doc/test"


@pytest.mark.unit
def test_convert_preserves_modified_time(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(updated_at="2026-03-15T10:00:00Z")
    result = list(converter.convert(doc))
    assert result[0]["modifiedTime"] == "2026-03-15T10:00:00Z"


@pytest.mark.unit
def test_chunks_include_title_as_first(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(title="My Doc Title")
    result = list(converter.convert(doc))
    chunks = result[0]["chunks"]
    assert chunks[0]["indexedData"] == "My Doc Title"


@pytest.mark.unit
def test_body_chunks_appended(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(text="body text")
    result = list(converter.convert(doc))
    chunks = result[0]["chunks"]
    texts = [c["indexedData"] for c in chunks]
    assert "mocked chunk text" in texts


@pytest.mark.unit
def test_attachment_chunk_has_metadata_key(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(
        attachments=[
            {
                "filename": "diagram.png",
                "bytes": base64.b64encode(b"fake").decode("ascii"),
                "mimeType": "image/png",
            }
        ]
    )
    result = list(converter.convert(doc))
    chunks = result[0]["chunks"]
    att_chunks = [c for c in chunks if c.get("metadata", {}).get("attachment")]
    assert len(att_chunks) > 0
    assert att_chunks[0]["metadata"]["attachment"] == "diagram.png"


@pytest.mark.unit
def test_chunks_carry_source_metadata(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(doc_id="doc1", url="https://example.com/doc/doc1")
    result = list(converter.convert(doc))
    chunks = result[0]["chunks"]
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        assert meta.get("sourceId") == "doc1"
        assert meta.get("sourceUrl") == "https://example.com/doc/doc1"
        assert "sourceUpdatedAt" in meta


@pytest.mark.unit
def test_empty_body_no_crash(converter) -> None:
    doc = _make_document(text="")
    result = list(converter.convert(doc))
    # Should not crash; title chunk still emitted
    assert len(result) == 1
    assert result[0]["chunks"][0]["indexedData"] == "My Document"


@pytest.mark.unit
def test_no_attachments_when_disabled() -> None:
    from connectors.outline.outline_document_converter import OutlineDocumentConverter

    c = OutlineDocumentConverter(include_attachments=False)
    mock_parser = MagicMock()
    chunk = MagicMock()
    chunk.contextualized_text = "body"
    chunk.metadata = {}
    mock_parser.parse_bytes.return_value = MagicMock(chunks=[chunk])
    c._parsing = mock_parser

    doc = _make_document(
        text="body",
        attachments=[
            {"filename": "secret.pdf", "bytes": b"data", "mimeType": "application/pdf"}
        ],
    )
    result = list(c.convert(doc))
    chunks = result[0]["chunks"]
    att_chunks = [ch for ch in chunks if ch.get("metadata", {}).get("attachment")]
    assert len(att_chunks) == 0


@pytest.mark.unit
def test_parse_attachment_failure_skipped(converter, mock_parser) -> None:
    mock_parser.parse_bytes.side_effect = [
        mock_parser.parse_bytes.return_value,  # body
        Exception("parse error"),  # attachment
    ]
    converter._parsing = mock_parser

    doc = _make_document(
        text="body",
        attachments=[
            {"filename": "bad.pdf", "bytes": b"garbage", "mimeType": "application/pdf"}
        ],
    )
    # Should not raise
    result = list(converter.convert(doc))
    assert len(result) == 1


@pytest.mark.unit
def test_full_text_contains_title_and_body(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(title="Title", text="Body content here.")
    result = list(converter.convert(doc))
    full_text = result[0]["text"]
    assert "Title" in full_text
    assert "Body content here." in full_text


@pytest.mark.unit
def test_modified_time_falls_back_to_created_at(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(updated_at="")
    doc["document"].pop("updatedAt", None)
    doc["document"]["createdAt"] = "2026-02-01T12:00:00Z"
    result = list(converter.convert(doc))
    assert result[0]["modifiedTime"] == "2026-02-01T12:00:00Z"


@pytest.mark.unit
def test_modified_time_falls_back_to_epoch_when_no_timestamps(
    converter, mock_parser
) -> None:
    converter._parsing = mock_parser
    doc = _make_document(updated_at="")
    doc["document"].pop("updatedAt", None)
    result = list(converter.convert(doc))
    assert result[0]["modifiedTime"] == "1970-01-01T00:00:00+00:00"


@pytest.mark.unit
def test_invalid_base64_attachment_skipped(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(
        text="body",
        attachments=[
            {
                "filename": "broken.png",
                "bytes": "not-valid-base64!!!",
                "mimeType": "image/png",
            }
        ],
    )
    result = list(converter.convert(doc))
    att_chunks = [
        c for c in result[0]["chunks"] if c.get("metadata", {}).get("attachment")
    ]
    assert att_chunks == []
