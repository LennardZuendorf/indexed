"""Tests for V1FormatAdapter."""

import os

from parsing.schema import ParsedChunk, ParsedDocument

from connectors.files.v1_adapter import V1FormatAdapter


def _make_parsed_doc(file_path: str) -> ParsedDocument:
    return ParsedDocument(
        file_path=file_path,
        chunks=[
            ParsedChunk(
                text="chunk one",
                contextualized_text="Heading\nchunk one",
                metadata={"headings": ["Heading"]},
                source_type="document",
            ),
            ParsedChunk(
                text="chunk two",
                contextualized_text="chunk two",
                metadata={},
                source_type="document",
            ),
        ],
        metadata={"format": ".txt", "modified_time": "2026-01-01T00:00:00"},
    )


class TestV1ReaderOutput:
    def test_keys_present(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        doc = _make_parsed_doc(str(f))
        result = V1FormatAdapter.reader_output(doc, str(tmp_path))

        assert "fileRelativePath" in result
        assert "fileFullPath" in result
        assert "modifiedTime" in result
        assert "content" in result

    def test_relative_path(self, tmp_path):
        f = tmp_path / "sub" / "doc.txt"
        f.parent.mkdir()
        f.write_text("hello")
        doc = _make_parsed_doc(str(f))
        result = V1FormatAdapter.reader_output(doc, str(tmp_path))

        assert result["fileRelativePath"] == os.path.join("sub", "doc.txt")

    def test_content_maps_chunks(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        doc = _make_parsed_doc(str(f))
        result = V1FormatAdapter.reader_output(doc, str(tmp_path))

        assert len(result["content"]) == 2
        assert result["content"][0]["text"] == "Heading\nchunk one"


class TestV1ConverterOutput:
    def test_structure(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        doc = _make_parsed_doc(str(f))
        result = V1FormatAdapter.converter_output(doc, str(tmp_path))

        assert isinstance(result, list)
        assert len(result) == 1
        entry = result[0]
        assert "id" in entry
        assert "url" in entry
        assert "text" in entry
        assert "chunks" in entry
        assert entry["url"].startswith("file://")

    def test_first_chunk_is_file_path(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        doc = _make_parsed_doc(str(f))
        result = V1FormatAdapter.converter_output(doc, str(tmp_path))

        chunks = result[0]["chunks"]
        assert chunks[0]["indexedData"] == "doc.txt"
        # Plus 2 real chunks
        assert len(chunks) == 3
