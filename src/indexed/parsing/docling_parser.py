"""Document parser backed by Docling.

Handles PDF, DOCX, PPTX, HTML, images, and other rich document formats.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from ._model_window import effective_max_tokens, get_markdown_chunker
from .schema import ParsedChunk, ParsedDocument

if TYPE_CHECKING:
    from docling.chunking import HybridChunker
    from docling.document_converter import DocumentConverter


class DoclingParser:
    """Parse rich documents using Docling's ``DocumentConverter`` + ``HybridChunker``."""

    def __init__(
        self,
        *,
        ocr: bool = True,
        table_structure: bool = True,
        max_tokens: int = 512,
    ) -> None:
        self._ocr = ocr
        self._table_structure = table_structure
        # Clamp to the embedder's real token window (bug A4) — see A1's fix
        # note in `_model_window.py`.
        self._max_tokens = effective_max_tokens(max_tokens)

        # Lazily initialised on first call to ``parse``.
        self._converter: DocumentConverter | None = None
        self._chunker: HybridChunker | None = None
        self._supported_extensions: frozenset[str] | None = None

    # -- lazy init --------------------------------------------------------

    def _ensure_converter(self) -> None:
        """Build the Docling converter & chunker once, then reuse."""
        if self._converter is not None:
            return

        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import (
            DocumentConverter,
            ImageFormatOption,
            PdfFormatOption,
        )

        pipeline_opts = PdfPipelineOptions()
        pipeline_opts.do_ocr = self._ocr
        pipeline_opts.do_table_structure = self._table_structure

        # Only PDF and IMAGE use the Pdf pipeline (PdfPipelineOptions has
        # do_ocr/do_table_structure). DOCX/PPTX/HTML/XLSX use SimplePipeline
        # with the base PipelineOptions, which has neither field — do not
        # attach Pdf pipeline options there (R14).
        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_opts),
            }
        )

        from docling.datamodel.base_models import FormatToExtensions

        self._supported_extensions = frozenset(
            f".{ext.lower()}" for exts in FormatToExtensions.values() for ext in exts
        )

        # Token-aware chunker (bug A1) — HierarchicalChunker silently dropped
        # max_tokens/include_metadata (neither is a real field on it).
        self._chunker = get_markdown_chunker()

    # -- public API -------------------------------------------------------

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse *file_path* and return a ``ParsedDocument``."""
        self._ensure_converter()
        assert self._converter is not None  # for type-checkers
        assert self._chunker is not None
        assert self._supported_extensions is not None

        # Skip files with extensions docling doesn't support — avoids noisy
        # ERROR logs from docling's DocumentConverter for unsupported formats.
        if file_path.suffix.lower() not in self._supported_extensions:
            return ParsedDocument(
                file_path=str(file_path),
                chunks=[],
                metadata={"format": file_path.suffix.lower(), "skipped": True},
            )

        try:
            result = self._converter.convert(str(file_path))
            doc = result.document

            raw_chunks = list(self._chunker.chunk(doc))

            chunks: list[ParsedChunk] = []
            for ch in raw_chunks:
                text = ch.text if hasattr(ch, "text") else str(ch)
                meta: dict[str, object] = {}
                if hasattr(ch, "meta"):
                    for key in ("headings", "page", "provenance"):
                        val = getattr(ch.meta, key, None)
                        if val is not None:
                            meta[key] = val

                contextualized = text
                headings = meta.get("headings")
                if isinstance(headings, (list, tuple)):
                    prefix = " > ".join(str(h) for h in headings)
                    contextualized = f"{prefix}\n{text}"

                chunks.append(
                    ParsedChunk(
                        text=text,
                        contextualized_text=contextualized,
                        metadata=meta,
                        source_type="document",
                    )
                )

            return ParsedDocument(
                file_path=str(file_path),
                chunks=chunks,
                metadata={
                    "format": file_path.suffix.lower(),
                    "size": file_path.stat().st_size if file_path.exists() else 0,
                },
            )

        except Exception:
            logger.debug("Docling could not parse {} (unsupported format)", file_path)
            return ParsedDocument(
                file_path=str(file_path),
                chunks=[],
                metadata={"format": file_path.suffix.lower(), "error": True},
            )
