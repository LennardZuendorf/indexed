"""Tests for parsing.ParsingModule — facade integration tests."""

from pathlib import Path

import pytest

from parsing import ParsingModule

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def module() -> ParsingModule:
    return ParsingModule(ocr=False, table_structure=False, max_tokens=512)


class TestParsingModule:
    def test_parse_python_routes_to_code(self, module: ParsingModule):
        doc = module.parse(FIXTURES / "sample.py")
        assert len(doc.chunks) > 0
        assert all(ch.source_type == "code" for ch in doc.chunks)

    def test_parse_typescript_routes_to_code(self, module: ParsingModule):
        doc = module.parse(FIXTURES / "sample.ts")
        assert len(doc.chunks) > 0
        assert all(ch.source_type == "code" for ch in doc.chunks)

    def test_parse_json_routes_to_plaintext(self, module: ParsingModule):
        doc = module.parse(FIXTURES / "sample.json")
        assert len(doc.chunks) > 0

    def test_parse_empty_file(self, module: ParsingModule):
        doc = module.parse(FIXTURES / "empty.txt")
        assert doc.chunks == []

    def test_parse_bytes(self, module: ParsingModule):
        content = b"Hello, this is a test document with some content."
        doc = module.parse_bytes(content, "test.txt")
        assert doc.file_path == "test.txt"
        assert len(doc.chunks) > 0

    def test_metadata_populated(self, module: ParsingModule):
        doc = module.parse(FIXTURES / "sample.py")
        assert "format" in doc.metadata
        assert doc.metadata["format"] == ".py"

    def test_css_routes_to_plaintext(self, module: ParsingModule, tmp_path: Path):
        css_file = tmp_path / "styles.css"
        css_file.write_text("body { color: red; }")
        doc = module.parse(css_file)
        assert len(doc.chunks) > 0
        assert doc.metadata.get("error") is not True

    def test_docling_fallback_succeeds_via_plaintext(
        self, module: ParsingModule, tmp_path: Path
    ):
        """Files with unknown extensions should fall back to plaintext without error."""
        unknown_file = tmp_path / ".gitignore"
        unknown_file.write_text("node_modules/\n.env\n")
        doc = module.parse(unknown_file)
        assert len(doc.chunks) > 0
        assert doc.metadata.get("error") is not True

    def test_docling_fallback_empty_file_no_error(
        self, module: ParsingModule, tmp_path: Path
    ):
        """Empty files via fallback should not be flagged as errors."""
        empty = tmp_path / ".hotreload"
        empty.write_text("")
        doc = module.parse(empty)
        assert doc.chunks == []
        assert doc.metadata.get("error") is not True
