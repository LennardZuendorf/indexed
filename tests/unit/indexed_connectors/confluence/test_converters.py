"""Tests for unified Confluence document converter."""

import pytest
from unittest.mock import MagicMock
from connectors.confluence.unified_confluence_document_converter import (
    UnifiedConfluenceDocumentConverter,
)

pytestmark = pytest.mark.connectors


def _make_server_doc(
    page_id="12345",
    title="Test Page",
    ancestors=None,
    body_html="<p>Hello World</p>",
    comments=None,
    attachments=None,
    modified="2024-01-01T12:00:00Z",
):
    """Build a Server/DC-style document dict."""
    page = {
        "id": page_id,
        "title": title,
        "ancestors": ancestors or [],
        "body": {"storage": {"value": body_html}},
        "version": {"when": modified},
        "_links": {
            "self": "https://confluence.example.com/rest/api/content/12345",
            "webui": "/display/SPACE/Test+Page",
        },
    }
    doc = {"page": page, "comments": comments or []}
    if attachments is not None:
        doc["attachments"] = attachments
    return doc


def _make_cloud_doc(
    page_id="12345",
    title="Test Page",
    ancestors=None,
    body_html="<p>Hello World</p>",
    comments=None,
    attachments=None,
    modified="2024-01-01T12:00:00Z",
):
    """Build a Cloud-style document dict (nested in content)."""
    content = {
        "id": page_id,
        "title": title,
        "ancestors": ancestors or [],
        "body": {"storage": {"value": body_html}},
        "version": {"when": modified},
        "_links": {
            "self": "https://company.atlassian.net/wiki/rest/api/content/12345",
            "webui": "/spaces/SPACE/pages/12345/Test+Page",
        },
    }
    doc = {"page": {"content": content}, "comments": comments or []}
    if attachments is not None:
        doc["attachments"] = attachments
    return doc


class TestUnifiedConfluenceDocumentConverter:
    """Test the unified converter for both Server and Cloud formats."""

    def test_server_basic_conversion(self):
        converter = UnifiedConfluenceDocumentConverter(is_cloud=False)
        doc = _make_server_doc()
        result = converter.convert(doc)

        assert len(result) == 1
        out = result[0]
        assert out["id"] == "12345"
        assert "Test Page" in out["text"]
        assert "Hello World" in out["text"]
        assert out["modifiedTime"] == "2024-01-01T12:00:00Z"
        assert out["chunks"][0]["indexedData"] == "Test Page"

    def test_cloud_basic_conversion(self):
        converter = UnifiedConfluenceDocumentConverter(is_cloud=True)
        doc = _make_cloud_doc()
        result = converter.convert(doc)

        assert len(result) == 1
        out = result[0]
        assert out["id"] == "12345"
        assert "Test Page" in out["text"]
        assert "Hello World" in out["text"]

    def test_title_hierarchy(self):
        converter = UnifiedConfluenceDocumentConverter(is_cloud=False)
        doc = _make_server_doc(
            ancestors=[{"title": "Parent"}, {"title": "Grandparent"}],
            title="Child Page",
        )
        result = converter.convert(doc)
        first_chunk = result[0]["chunks"][0]["indexedData"]
        assert first_chunk == "Parent -> Grandparent -> Child Page"

    def test_comments_included(self):
        converter = UnifiedConfluenceDocumentConverter(is_cloud=False)
        comments = [
            {"body": {"storage": {"value": "<p>First comment</p>"}}},
            {"body": {"storage": {"value": "<p>Second comment</p>"}}},
        ]
        doc = _make_server_doc(comments=comments)
        result = converter.convert(doc)
        text = result[0]["text"]
        assert "First comment" in text
        assert "Second comment" in text

    def test_empty_body(self):
        converter = UnifiedConfluenceDocumentConverter(is_cloud=False)
        doc = _make_server_doc(body_html="")
        result = converter.convert(doc)
        assert result[0]["id"] == "12345"

    def test_url_building_server(self):
        converter = UnifiedConfluenceDocumentConverter(is_cloud=False)
        doc = _make_server_doc()
        result = converter.convert(doc)
        assert (
            result[0]["url"] == "https://confluence.example.com/display/SPACE/Test+Page"
        )

    def test_url_building_cloud(self):
        converter = UnifiedConfluenceDocumentConverter(is_cloud=True)
        doc = _make_cloud_doc()
        result = converter.convert(doc)
        assert (
            result[0]["url"]
            == "https://company.atlassian.net/wiki/spaces/SPACE/pages/12345/Test+Page"
        )

    def test_chunks_use_parsing_module(self):
        """Verify that chunks come from ParsingModule, not RecursiveCharacterTextSplitter."""
        converter = UnifiedConfluenceDocumentConverter(is_cloud=False)
        doc = _make_server_doc(body_html="<p>Paragraph one.</p><p>Paragraph two.</p>")
        result = converter.convert(doc)
        chunks = result[0]["chunks"]
        # First chunk is title, rest are from ParsingModule
        assert len(chunks) >= 2
        assert chunks[0]["indexedData"] == "Test Page"

    def test_attachment_parsing(self):
        """Test that attachment bytes are parsed via ParsingModule."""
        mock_parsed = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.contextualized_text = "Parsed attachment content"
        mock_chunk.metadata = {"headings": ["Section 1"]}
        mock_parsed.chunks = [mock_chunk]

        # Also mock the text parse_bytes call
        mock_text_parsed = MagicMock()
        mock_text_chunk = MagicMock()
        mock_text_chunk.contextualized_text = "Hello World"
        mock_text_chunk.metadata = {}
        mock_text_parsed.chunks = [mock_text_chunk]

        converter = UnifiedConfluenceDocumentConverter(
            is_cloud=False, include_attachments=True
        )

        mock_parser = MagicMock()
        mock_parser.parse_bytes.side_effect = (
            lambda data, filename: mock_parsed
            if filename == "report.pdf"
            else mock_text_parsed
        )
        converter._parsing = mock_parser

        attachments = [
            {
                "filename": "report.pdf",
                "bytes": b"fake pdf bytes",
                "mimeType": "application/pdf",
            },
        ]
        doc = _make_server_doc(attachments=attachments)
        result = converter.convert(doc)

        chunks = result[0]["chunks"]
        att_chunks = [c for c in chunks if c.get("metadata", {}).get("attachment")]
        assert len(att_chunks) == 1
        assert att_chunks[0]["indexedData"] == "Parsed attachment content"
        assert att_chunks[0]["metadata"]["attachment"] == "report.pdf"

    def test_attachments_skipped_when_disabled(self):
        """Attachments should be ignored when include_attachments=False."""
        converter = UnifiedConfluenceDocumentConverter(
            is_cloud=False, include_attachments=False
        )
        doc = _make_server_doc(attachments=[{"filename": "test.pdf", "bytes": b"data"}])
        result = converter.convert(doc)
        chunks = result[0]["chunks"]
        att_chunks = [c for c in chunks if c.get("metadata", {}).get("attachment")]
        assert len(att_chunks) == 0

    def test_attachment_parse_error_handled_gracefully(self):
        """Failed attachment parsing should log warning and continue."""
        converter = UnifiedConfluenceDocumentConverter(
            is_cloud=False, include_attachments=True
        )

        mock_parser = MagicMock()
        # Text parsing works, attachment parsing fails
        mock_text_parsed = MagicMock()
        mock_text_parsed.chunks = []

        def side_effect(data, filename):
            if filename == "bad.bin":
                raise Exception("parse failed")
            return mock_text_parsed

        mock_parser.parse_bytes.side_effect = side_effect
        converter._parsing = mock_parser

        doc = _make_server_doc(
            attachments=[{"filename": "bad.bin", "bytes": b"\x00\x01\x02"}]
        )
        result = converter.convert(doc)

        # Should still return results without crashing
        assert len(result) == 1
