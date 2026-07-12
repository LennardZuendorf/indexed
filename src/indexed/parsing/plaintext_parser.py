"""Plaintext / Markdown parser.

Markdown is parsed via Docling (which supports it natively) for
structure-aware chunking with heading hierarchy.  Everything else
(txt, json, yaml, csv, …) is split at paragraph/sentence boundaries.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from ._model_window import count_tokens, effective_max_tokens, get_markdown_chunker
from .schema import ParsedChunk, ParsedDocument


class PlaintextParser:
    """Parse plain-text and markdown files."""

    def __init__(self, *, max_tokens: int = 512) -> None:
        # Clamp to the embedder's real token window (bug A4) — a requested
        # budget above the model's max_seq_length would otherwise produce
        # chunks whose tail is silently truncated at embed time.
        self._max_tokens = effective_max_tokens(max_tokens)
        self._max_chars = self._max_tokens * 4  # rough estimate, last-resort fallback

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

            converter = DocumentConverter()
            result = converter.convert(str(file_path))
            doc = result.document

            chunker = get_markdown_chunker()
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
                headings = meta.get("headings")
                if isinstance(headings, (list, tuple)):
                    prefix = " > ".join(str(h) for h in headings)
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
        """Split *text* into window-sized chunks.

        Splits on blank-line paragraph boundaries first (prose); falls back to
        single newlines when there are none (CSV/JSON/YAML/log/XML — bug A3),
        and to a hard word/character window when even a single paragraph or
        line alone exceeds the model's token window (bug A1/A4). Every chunk
        this returns tokenizes to at most ``self._max_tokens`` under the
        default embedding tokenizer.
        """
        if count_tokens(text) <= self._max_tokens:
            return [self._make_plaintext_chunk(text, file_path)]

        units = text.split("\n\n")
        sep = "\n\n"
        if len(units) == 1:
            units = text.split("\n")
            sep = "\n"

        pieces: list[str] = []
        for unit in units:
            pieces.extend(self._bound_to_window(unit))

        chunks: list[ParsedChunk] = []
        buf: list[str] = []
        buf_tokens = 0

        for piece in pieces:
            piece_tokens = count_tokens(piece)
            if buf and buf_tokens + piece_tokens > self._max_tokens:
                chunks.append(self._make_plaintext_chunk(sep.join(buf), file_path))
                buf = []
                buf_tokens = 0
            buf.append(piece)
            buf_tokens += piece_tokens

        if buf:
            chunks.append(self._make_plaintext_chunk(sep.join(buf), file_path))

        return chunks

    def _bound_to_window(self, unit: str) -> list[str]:
        """Split *unit* further if it alone exceeds the token window."""
        if count_tokens(unit) <= self._max_tokens:
            return [unit]

        words = unit.split(" ")
        if len(words) == 1:
            # A single unsplittable run (no spaces) — hard-slice by
            # characters as a last resort.
            return self._slice_by_chars(unit)

        out: list[str] = []
        buf: list[str] = []
        buf_tokens = 0
        for word in words:
            word_tokens = count_tokens(word)
            if word_tokens > self._max_tokens:
                # A single word alone overflows the window (a base64 blob,
                # URL, hash, or JWT embedded in an otherwise multi-word
                # line/paragraph) — flush what's buffered, then hard-slice
                # this word too, so it never survives into an oversize chunk.
                if buf:
                    out.append(" ".join(buf))
                    buf = []
                    buf_tokens = 0
                out.extend(self._slice_by_chars(word))
                continue
            if buf and buf_tokens + word_tokens > self._max_tokens:
                out.append(" ".join(buf))
                buf = []
                buf_tokens = 0
            buf.append(word)
            buf_tokens += word_tokens
        if buf:
            out.append(" ".join(buf))
        return out

    def _slice_by_chars(self, text: str) -> list[str]:
        """Hard-slice *text* by characters as a last resort.

        Used for unsplittable runs with no internal spaces — either a whole
        unit (line/paragraph) or a single oversized word found mid-unit
        (e.g. a base64 blob, URL, hash, or JWT). Conservative ratio so the
        slice stays inside the window even for dense (punctuation-heavy) text.
        """
        step = max(1, self._max_chars // 4)
        return [text[i : i + step] for i in range(0, len(text), step)] or [text]

    def _make_plaintext_chunk(self, text: str, file_path: str) -> ParsedChunk:
        return ParsedChunk(
            text=text,
            contextualized_text=f"{file_path}\n{text}",
            metadata={"file_path": file_path},
            source_type="plaintext",
        )
