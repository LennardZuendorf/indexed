"""Tests for parsing.router — FileRouter."""

from pathlib import Path

import pytest

from parsing.router import (
    CODE_EXTENSIONS,
    DOCLING_EXTENSIONS,
    PLAINTEXT_EXTENSIONS,
    FileRouter,
    ParsingStrategy,
)


@pytest.fixture
def router() -> FileRouter:
    return FileRouter()


class TestFileRouter:
    def test_code_extensions(self, router: FileRouter):
        for ext in (".py", ".ts", ".tsx", ".js", ".java", ".rs", ".go", ".c", ".cpp"):
            assert router.route(Path(f"file{ext}")) == ParsingStrategy.CODE_AST

    def test_docling_extensions(self, router: FileRouter):
        for ext in (".pdf", ".docx", ".pptx", ".html", ".htm"):
            assert router.route(Path(f"file{ext}")) == ParsingStrategy.DOCLING

    def test_plaintext_extensions(self, router: FileRouter):
        for ext in (".md", ".txt", ".json", ".yaml", ".toml", ".csv"):
            assert router.route(Path(f"file{ext}")) == ParsingStrategy.PLAINTEXT

    def test_unknown_extension_fallback(self, router: FileRouter):
        assert router.route(Path("file.xyz")) == ParsingStrategy.DOCLING_FALLBACK
        assert router.route(Path("file.weird")) == ParsingStrategy.DOCLING_FALLBACK

    def test_case_insensitive(self, router: FileRouter):
        assert router.route(Path("file.PY")) == ParsingStrategy.CODE_AST
        assert router.route(Path("file.PDF")) == ParsingStrategy.DOCLING
        assert router.route(Path("file.MD")) == ParsingStrategy.PLAINTEXT

    def test_extension_sets_no_overlap(self):
        """Extension sets must not overlap."""
        assert CODE_EXTENSIONS.isdisjoint(DOCLING_EXTENSIONS)
        assert CODE_EXTENSIONS.isdisjoint(PLAINTEXT_EXTENSIONS)
        assert DOCLING_EXTENSIONS.isdisjoint(PLAINTEXT_EXTENSIONS)
