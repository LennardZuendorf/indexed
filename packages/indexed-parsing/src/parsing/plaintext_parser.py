"""Plaintext / Markdown parser.

Markdown is parsed via Docling (which supports it natively) for
structure-aware chunking with heading hierarchy.  Everything else
(txt, json, yaml, csv, …) is split at paragraph/sentence boundaries.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from .schema import ParsedChunk, ParsedDocument


class PlaintextParser:
    """Parse plain-text and markdown files."""

    def __init__(self, *, max_tokens: int = 512) -> None:
        self._max_tokens = max_tokens
        self._max_chars = max_tokens * 4  # rough estimate

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse *file_path* and return a ``ParsedDocument``."""
        ext = file_path.suffix.lower()

        # Only Markdown goes through Docling (which natively supports it).
        # .rst falls through to the generic path — Docling has no InputFormat
        # for reST and would emit a per-file ERROR before we caught the
        # exception. See docs/plans/2026-04-25-001-refactor-cli-logging-pipeline-plan.md U7.
        if ext == ".md":
            return self._parse_markdown(file_path)
        return self._parse_generic(file_path)

    # -- markdown via Docling ---------------------------------------------

    def _parse_markdown(self, file_path: Path) -> ParsedDocument:
        """Use Docling for structure-aware markdown chunking."""
        try:
            from docling.document_converter import DocumentConverter
            from docling_core.transforms.chunker import HierarchicalChunker

            converter = DocumentConverter()
            result = converter.convert(str(file_path))
            doc = result.document

            chunker = HierarchicalChunker(
                max_tokens=self._max_tokens,
                include_metadata=True,
            )
            raw_chunks = list(chunker.chunk(doc))

            chunks: list[ParsedChunk] = []
            for ch in raw_chunks:
                text = ch.text if hasattr(ch, "text") else str(ch)
                meta: dict[str, object] = {}
                if hasattr(ch, "meta"):
                    for key in ("headings", "page", "provenance"):
                        val = getattr(ch.meta, key, None)
                        if val is not None:
                            meta[key] = val

                ctx = text
                if meta.get("headings"):
                    prefix = " > ".join(str(h) for h in meta["headings"])  # type: ignore[union-attr]
                    ctx = f"{prefix}\n{text}"

                chunks.append(
                    ParsedChunk(
                        text=text,
                        contextualized_text=ctx,
                        metadata=meta,
                        source_type="document",
                    )
                )

            return ParsedDocument(
                file_path=str(file_path),
                chunks=chunks,
                metadata={
                    "format": file_path.suffix.lower(),
                    "size": file_path.stat().st_size,
                },
            )

        except Exception:
            logger.opt(exception=True).debug(
                "Docling markdown parsing failed for {}; using generic parser",
                file_path,
            )
            return self._parse_generic(file_path)

    # -- generic text files -----------------------------------------------

    def _parse_generic(self, file_path: Path) -> ParsedDocument:
        """Read as text and split at paragraph boundaries."""
        try:
            text = file_path.read_text(errors="replace")
        except Exception:
            logger.opt(exception=True).warning("Cannot read {}", file_path)
            return ParsedDocument(
                file_path=str(file_path),
                chunks=[],
                metadata={"format": file_path.suffix.lower(), "error": True},
            )

        if not text.strip():
            return ParsedDocument(
                file_path=str(file_path),
                chunks=[],
                metadata={"format": file_path.suffix.lower(), "size": 0},
            )

        chunks = self._split_paragraphs(text, str(file_path))

        return ParsedDocument(
            file_path=str(file_path),
            chunks=chunks,
            metadata={
                "format": file_path.suffix.lower(),
                "size": file_path.stat().st_size,
            },
        )

    def _split_paragraphs(self, text: str, file_path: str) -> list[ParsedChunk]:
        """Split *text* into chunks at paragraph boundaries."""
        if len(text) <= self._max_chars:
            return [
                ParsedChunk(
                    text=text,
                    contextualized_text=f"{file_path}\n{text}",
                    metadata={"file_path": file_path},
                    source_type="plaintext",
                )
            ]

        paragraphs = text.split("\n\n")
        chunks: list[ParsedChunk] = []
        buf: list[str] = []
        buf_len = 0

        for para in paragraphs:
            para_len = len(para)
            if buf_len + para_len + 2 > self._max_chars and buf:
                chunk_text = "\n\n".join(buf)
                chunks.append(
                    ParsedChunk(
                        text=chunk_text,
                        contextualized_text=f"{file_path}\n{chunk_text}",
                        metadata={"file_path": file_path},
                        source_type="plaintext",
                    )
                )
                buf.clear()
                buf_len = 0

            buf.append(para)
            buf_len += para_len + 2

        if buf:
            chunk_text = "\n\n".join(buf)
            chunks.append(
                ParsedChunk(
                    text=chunk_text,
                    contextualized_text=f"{file_path}\n{chunk_text}",
                    metadata={"file_path": file_path},
                    source_type="plaintext",
                )
            )

        return chunks
