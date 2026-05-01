"""Tests for OutlineDocumentConverter chunk emission, title path, and attachment parsing."""

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

    return OutlineDocumentConverter(max_chunk_tokens=512, ocr=False, include_attachments=True)


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


def test_convert_returns_list_with_one_entry(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document()
    result = converter.convert(doc)
    assert len(result) == 1


def test_convert_preserves_id(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(doc_id="abc-123")
    result = converter.convert(doc)
    assert result[0]["id"] == "abc-123"


def test_convert_preserves_url(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(url="https://app.getoutline.com/doc/test")
    result = converter.convert(doc)
    assert result[0]["url"] == "https://app.getoutline.com/doc/test"


def test_convert_preserves_modified_time(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(updated_at="2026-03-15T10:00:00Z")
    result = converter.convert(doc)
    assert result[0]["modifiedTime"] == "2026-03-15T10:00:00Z"


def test_chunks_include_title_as_first(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(title="My Doc Title")
    result = converter.convert(doc)
    chunks = result[0]["chunks"]
    assert chunks[0]["indexedData"] == "My Doc Title"


def test_body_chunks_appended(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(text="body text")
    result = converter.convert(doc)
    chunks = result[0]["chunks"]
    texts = [c["indexedData"] for c in chunks]
    assert "mocked chunk text" in texts


def test_attachment_chunk_has_metadata_key(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(
        attachments=[{"filename": "diagram.png", "bytes": b"fake", "mimeType": "image/png"}]
    )
    result = converter.convert(doc)
    chunks = result[0]["chunks"]
    att_chunks = [c for c in chunks if c.get("metadata", {}).get("attachment")]
    assert len(att_chunks) > 0
    assert att_chunks[0]["metadata"]["attachment"] == "diagram.png"


def test_empty_body_no_crash(converter) -> None:
    doc = _make_document(text="")
    result = converter.convert(doc)
    # Should not crash; title chunk still emitted
    assert len(result) == 1
    assert result[0]["chunks"][0]["indexedData"] == "My Document"


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
        attachments=[{"filename": "secret.pdf", "bytes": b"data", "mimeType": "application/pdf"}],
    )
    result = c.convert(doc)
    chunks = result[0]["chunks"]
    att_chunks = [ch for ch in chunks if ch.get("metadata", {}).get("attachment")]
    assert len(att_chunks) == 0


def test_parse_attachment_failure_skipped(converter, mock_parser) -> None:
    mock_parser.parse_bytes.side_effect = [
        mock_parser.parse_bytes.return_value,  # body
        Exception("parse error"),  # attachment
    ]
    converter._parsing = mock_parser

    doc = _make_document(
        text="body",
        attachments=[{"filename": "bad.pdf", "bytes": b"garbage", "mimeType": "application/pdf"}],
    )
    # Should not raise
    result = converter.convert(doc)
    assert len(result) == 1


def test_full_text_contains_title_and_body(converter, mock_parser) -> None:
    converter._parsing = mock_parser
    doc = _make_document(title="Title", text="Body content here.")
    result = converter.convert(doc)
    full_text = result[0]["text"]
    assert "Title" in full_text
    assert "Body content here." in full_text
