"""Tests for parsing.plaintext_parser — PlaintextParser."""

from pathlib import Path

import pytest

from parsing.plaintext_parser import PlaintextParser

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def parser() -> PlaintextParser:
    return PlaintextParser(max_tokens=512)


class TestPlaintextParser:
    def test_parse_json(self, parser: PlaintextParser):
        doc = parser.parse(FIXTURES / "sample.json")
        assert len(doc.chunks) > 0
        assert doc.metadata["format"] == ".json"

    def test_parse_empty_file(self, parser: PlaintextParser):
        doc = parser.parse(FIXTURES / "empty.txt")
        assert doc.chunks == []

    def test_parse_generic_text(self, parser: PlaintextParser, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("Hello world\n\nSecond paragraph.")
        doc = parser.parse(f)
        assert len(doc.chunks) >= 1
        assert doc.metadata["format"] == ".txt"
        assert doc.chunks[0].source_type == "plaintext"

    def test_long_text_splits(self, parser: PlaintextParser, tmp_path: Path):
        f = tmp_path / "long.txt"
        # Make text that exceeds max_chars (512 * 4 = 2048)
        paragraphs = ["This is a paragraph. " * 50 for _ in range(10)]
        f.write_text("\n\n".join(paragraphs))
        doc = parser.parse(f)
        assert len(doc.chunks) > 1

    def test_contextualized_text_includes_path(
        self, parser: PlaintextParser, tmp_path: Path
    ):
        f = tmp_path / "ctx.txt"
        f.write_text("Content here.")
        doc = parser.parse(f)
        assert str(f) in doc.chunks[0].contextualized_text

    def test_nonexistent_file(self, parser: PlaintextParser):
        doc = parser.parse(Path("/nonexistent/file.txt"))
        assert doc.chunks == []
        assert doc.metadata.get("error") is True
