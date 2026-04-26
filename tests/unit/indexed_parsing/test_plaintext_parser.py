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

    def test_parse_rst_does_not_invoke_docling(
        self, parser: PlaintextParser, tmp_path: Path, monkeypatch
    ):
        """Regression: .rst must NOT be routed through docling.

        See docs/plans/2026-04-25-001-refactor-cli-logging-pipeline-plan.md U7.
        Docling has no InputFormat for .rst and emits an ERROR per file when
        fed one. The fix routes .rst straight to the generic plaintext path.
        """
        import docling.document_converter as dc_module

        called = {"count": 0}
        original = dc_module.DocumentConverter

        def counting(*args, **kwargs):
            called["count"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(dc_module, "DocumentConverter", counting)

        f = tmp_path / "README.rst"
        f.write_text(
            "Title\n=====\n\nFirst paragraph.\n\nSecond paragraph with text.\n"
        )

        doc = parser.parse(f)

        # Even via the catch-and-fall-back path, docling must not be reached.
        assert called["count"] == 0, (
            "DocumentConverter was instantiated for a .rst file — the routing "
            "fix in PlaintextParser._parse_markdown is missing or regressed."
        )
        assert len(doc.chunks) >= 1
        assert doc.metadata["format"] == ".rst"
        assert doc.chunks[0].source_type == "plaintext"

    def test_parse_md_still_attempts_docling(
        self, parser: PlaintextParser, tmp_path: Path, monkeypatch
    ):
        """.md should still go to docling first (intentional)."""
        import docling.document_converter as dc_module

        called = {"count": 0}
        original = dc_module.DocumentConverter

        def counting(*args, **kwargs):
            called["count"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(dc_module, "DocumentConverter", counting)

        f = tmp_path / "doc.md"
        f.write_text("# Heading\n\nMarkdown body.\n")

        parser.parse(f)
        assert called["count"] == 1
