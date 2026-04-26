"""Tests for parsing.code_chunker — CodeChunker."""

from pathlib import Path

import pytest

from parsing.code_chunker import CodeChunker

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def chunker() -> CodeChunker:
    return CodeChunker(max_tokens=512)


class TestCodeChunkerPython:
    def test_chunks_python_file(self, chunker: CodeChunker):
        chunks = chunker.chunk_file(FIXTURES / "sample.py")
        assert len(chunks) > 0

    def test_python_semantic_boundaries(self, chunker: CodeChunker):
        chunks = chunker.chunk_file(FIXTURES / "sample.py")
        node_types = {ch.metadata.get("node_type") for ch in chunks}
        # Should find class and function definitions
        assert "class_definition" in node_types or "function_definition" in node_types

    def test_python_metadata_populated(self, chunker: CodeChunker):
        chunks = chunker.chunk_file(FIXTURES / "sample.py")
        for ch in chunks:
            assert ch.metadata.get("language") == "python"
            assert "start_line" in ch.metadata
            assert "end_line" in ch.metadata
            assert ch.source_type == "code"

    def test_python_contextualized_text(self, chunker: CodeChunker):
        chunks = chunker.chunk_file(FIXTURES / "sample.py")
        for ch in chunks:
            # Contextualized text should include the file path
            assert str(FIXTURES / "sample.py") in ch.contextualized_text


class TestCodeChunkerTypeScript:
    def test_chunks_typescript_file(self, chunker: CodeChunker):
        chunks = chunker.chunk_file(FIXTURES / "sample.ts")
        assert len(chunks) > 0

    def test_typescript_metadata(self, chunker: CodeChunker):
        chunks = chunker.chunk_file(FIXTURES / "sample.ts")
        for ch in chunks:
            assert ch.metadata.get("language") == "typescript"
            assert ch.source_type == "code"


class TestCodeChunkerEdgeCases:
    def test_empty_file(self, chunker: CodeChunker, tmp_path: Path):
        empty = tmp_path / "empty.py"
        empty.write_text("")
        chunks = chunker.chunk_file(empty)
        assert chunks == []

    def test_unknown_language(self, chunker: CodeChunker, tmp_path: Path):
        f = tmp_path / "file.rb"
        f.write_text("puts 'hello'\ndef greet\n  puts 'hi'\nend\n")
        chunks = chunker.chunk_file(f)
        # Falls back to line-based chunking
        assert len(chunks) > 0
        assert chunks[0].metadata.get("language") == "unknown"

    def test_nonexistent_file(self, chunker: CodeChunker):
        chunks = chunker.chunk_file(Path("/nonexistent/file.py"))
        assert chunks == []
