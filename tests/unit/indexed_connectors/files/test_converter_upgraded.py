"""Tests for the upgraded FilesDocumentConverter."""

from connectors.files.files_document_converter import FilesDocumentConverter


def _make_v1_reader_doc():
    return {
        "fileRelativePath": "docs/readme.txt",
        "fileFullPath": "/tmp/docs/readme.txt",
        "modifiedTime": "2026-01-01T00:00:00",
        "content": [
            {"text": "First chunk of content", "metadata": {"page": 1}},
            {"text": "Second chunk of content", "metadata": {}},
        ],
    }


class TestFilesDocumentConverter:
    def test_convert_returns_list(self):
        converter = FilesDocumentConverter()
        result = converter.convert(_make_v1_reader_doc())
        assert isinstance(result, list)
        assert len(result) == 1

    def test_convert_structure(self):
        converter = FilesDocumentConverter()
        result = converter.convert(_make_v1_reader_doc())[0]
        assert result["id"] == "docs/readme.txt"
        assert result["url"] == "file:///tmp/docs/readme.txt"
        assert "modifiedTime" in result
        assert "text" in result
        assert "chunks" in result

    def test_first_chunk_is_file_path(self):
        converter = FilesDocumentConverter()
        result = converter.convert(_make_v1_reader_doc())[0]
        assert result["chunks"][0]["indexedData"] == "docs/readme.txt"

    def test_content_chunks_mapped(self):
        converter = FilesDocumentConverter()
        result = converter.convert(_make_v1_reader_doc())[0]
        # File path chunk + 2 content chunks
        assert len(result["chunks"]) == 3
        assert result["chunks"][1]["indexedData"] == "First chunk of content"

    def test_empty_content_skipped(self):
        doc = _make_v1_reader_doc()
        doc["content"] = [
            {"text": "   ", "metadata": {}},
            {"text": "real", "metadata": {}},
        ]
        converter = FilesDocumentConverter()
        result = converter.convert(doc)[0]
        # File path chunk + 1 real chunk (whitespace-only skipped)
        assert len(result["chunks"]) == 2
