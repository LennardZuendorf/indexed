"""indexed-parsing — reusable document parsing module.

Composes a file router with Docling, tree-sitter, and plaintext parsers
to provide a single ``ParsingModule.parse()`` entry-point.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .code_chunker import CodeChunker
from .docling_parser import DoclingParser
from .plaintext_parser import PlaintextParser
from .router import FileRouter, ParsingStrategy
from .schema import ParsedChunk, ParsedDocument

__all__ = [
    "ParsingModule",
    "ParsedChunk",
    "ParsedDocument",
    "FileRouter",
    "ParsingStrategy",
    "DoclingParser",
    "CodeChunker",
    "PlaintextParser",
]


class ParsingModule:
    """Facade that routes files to the correct parser."""

    def __init__(
        self,
        *,
        ocr: bool = True,
        table_structure: bool = True,
        max_tokens: int = 512,
    ) -> None:
        self._router = FileRouter()
        self._docling = DoclingParser(
            ocr=ocr,
            table_structure=table_structure,
            max_tokens=max_tokens,
        )
        self._code = CodeChunker(max_tokens=max_tokens)
        self._plaintext = PlaintextParser(max_tokens=max_tokens)

    def parse(self, path: Path) -> ParsedDocument:
        """Parse a file and return a ``ParsedDocument``."""
        strategy = self._router.route(path)

        if strategy == ParsingStrategy.CODE_AST:
            chunks = self._code.chunk_file(path)
            return ParsedDocument(
                file_path=str(path),
                chunks=chunks,
                metadata={
                    "format": path.suffix.lower(),
                    "size": path.stat().st_size if path.exists() else 0,
                },
            )

        if strategy == ParsingStrategy.DOCLING:
            return self._docling.parse(path)

        if strategy == ParsingStrategy.PLAINTEXT:
            return self._plaintext.parse(path)

        # DOCLING_FALLBACK — try Docling, fall back to plaintext
        doc = self._docling.parse(path)
        if doc.chunks:
            return doc
        return self._plaintext.parse(path)

    def parse_bytes(self, data: bytes, filename: str) -> ParsedDocument:
        """Parse in-memory bytes (e.g. from Confluence attachments)."""
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp.flush()
            tmp_path = Path(tmp.name)

        try:
            doc = self.parse(tmp_path)
            # Replace temp path with the original filename
            doc.file_path = filename
            return doc
        finally:
            tmp_path.unlink(missing_ok=True)
