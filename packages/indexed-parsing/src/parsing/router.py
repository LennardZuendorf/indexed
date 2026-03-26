"""File router — maps file extensions to parsing strategies."""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class ParsingStrategy(Enum):
    """Strategy used to parse a file."""

    DOCLING = "docling"
    CODE_AST = "code_ast"
    PLAINTEXT = "plaintext"
    DOCLING_FALLBACK = "docling_fallback"


# Extension sets ----------------------------------------------------------

CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".rs",
        ".go",
        ".rb",
        ".cs",
        ".swift",
        ".kt",
        ".scala",
        ".sh",
        ".sql",
        ".proto",
        ".lua",
        ".r",
    }
)

DOCLING_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".html",
        ".htm",
        ".png",
        ".jpg",
        ".jpeg",
        ".tiff",
        ".tex",
    }
)

PLAINTEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".txt",
        ".rst",
        ".csv",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".xml",
        ".ini",
        ".cfg",
        ".env",
        ".log",
    }
)


class FileRouter:
    """Route a file path to the appropriate parsing strategy."""

    def route(self, path: Path) -> ParsingStrategy:
        """Return the parsing strategy for *path* based on its extension.

        The comparison is case-insensitive.
        """
        ext = path.suffix.lower()

        if ext in CODE_EXTENSIONS:
            return ParsingStrategy.CODE_AST
        if ext in DOCLING_EXTENSIONS:
            return ParsingStrategy.DOCLING
        if ext in PLAINTEXT_EXTENSIONS:
            return ParsingStrategy.PLAINTEXT
        return ParsingStrategy.DOCLING_FALLBACK
