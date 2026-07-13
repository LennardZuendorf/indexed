"""Tests for parsing.code_chunker — CodeChunker."""

from pathlib import Path

import pytest

from indexed.parsing._model_window import count_tokens
from indexed.parsing.code_chunker import CodeChunker

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


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


class TestCodeChunkerTokenBounds:
    """R12.1/R12.2/R12.3 — real token-window bounds, not the char estimate."""

    def test_dense_node_bounded_by_real_tokens(self, tmp_path: Path):
        """R12.1: `len(text) > self._max_chars` alone is insufficient — a
        semantic node whose text is under the (rough) char estimate but
        tokenizes over the real token window must still be split, not
        emitted as one oversized chunk.
        """
        chunker = CodeChunker(max_tokens=25)  # max_chars = 25 * 4 = 100
        # Symbol-dense text: the tokenizer emits close to one token per
        # character here, so this stays well under the char bound but
        # blows through the token bound.
        body = "!@#$%^&*()_+-=~`|\\][{}"
        code = f'def f():\n    return "{body}"\n'
        assert len(code) <= chunker._max_chars, "fixture must stay under the char bound"
        assert count_tokens(code) > chunker._max_tokens, (
            "fixture must exceed the token bound to reproduce R12.1"
        )

        f = tmp_path / "dense.py"
        f.write_text(code)
        chunks = chunker.chunk_file(f)

        for ch in chunks:
            tokens = count_tokens(ch.text)
            assert tokens <= chunker._max_tokens, (
                f"chunk of node_type={ch.metadata.get('node_type')!r} has "
                f"{tokens} tokens, exceeding the {chunker._max_tokens}-token budget"
            )

    def test_accumulator_bounded_by_real_tokens(self, tmp_path: Path):
        """R12.2: the between-nodes accumulator has no size guard before
        flush — 400 tiny statements must not collapse into one oversized
        `accumulated` chunk.
        """
        chunker = CodeChunker(max_tokens=50)
        lines = [f"x{i} = {i}" for i in range(400)]
        f = tmp_path / "many_statements.py"
        f.write_text("\n".join(lines) + "\n")

        chunks = chunker.chunk_file(f)

        accumulated = [
            ch for ch in chunks if ch.metadata.get("node_type") == "accumulated"
        ]
        assert accumulated, "expected at least one accumulated chunk"
        for ch in accumulated:
            tokens = count_tokens(ch.text)
            assert tokens <= chunker._max_tokens, (
                f"accumulated chunk has {tokens} tokens, exceeding the "
                f"{chunker._max_tokens}-token budget"
            )

    def test_accumulator_start_line_zero_preserved(self, tmp_path: Path):
        """R12.3: `acc_start or child.start_point[0]` drops a legitimate
        row-0 `acc_start` because 0 is falsy, so a file whose first lines
        are comments reports a bogus (backwards) line range instead of
        start_line == 0.
        """
        chunker = CodeChunker(max_tokens=512)
        code = "# comment line\n# comment line 2\n\ndef f():\n    pass\n"
        f = tmp_path / "leading_comments.py"
        f.write_text(code)

        chunks = chunker.chunk_file(f)

        accumulated = [
            ch for ch in chunks if ch.metadata.get("node_type") == "accumulated"
        ]
        assert accumulated, "expected a leading accumulated chunk for the comments"
        first = accumulated[0]
        assert first.metadata["start_line"] == 0
        assert first.metadata["start_line"] <= first.metadata["end_line"]


class TestCodeChunkerTsx:
    """.tsx (P3) — must parse with the tsx grammar, not plain typescript."""

    def test_tsx_uses_tsx_grammar(self, tmp_path: Path):
        """`tree_sitter_typescript` lacks a `language` attr so `_get_language`
        falls to `language_typescript()`, which doesn't understand JSX and
        fragments the AST around JSX syntax (the closing tag gets peeled off
        into a separate "accumulated" chunk). With the tsx grammar
        (`language_tsx()`), the whole function parses as one semantic node.
        """
        chunker = CodeChunker(max_tokens=512)
        code = (
            "export function Greet(props) {\n"
            '  return <div className="greeting">Hello {props.name}</div>;\n'
            "}\n"
        )
        f = tmp_path / "widget.tsx"
        f.write_text(code)

        chunks = chunker.chunk_file(f)

        node_types = [ch.metadata.get("node_type") for ch in chunks]
        assert "accumulated" not in node_types, (
            f"JSX fragmented the AST — got chunks {node_types}; .tsx is "
            "likely still parsing with language_typescript() instead of "
            "language_tsx()"
        )
