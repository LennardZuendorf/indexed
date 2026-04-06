"""Document parser backed by Docling.

Handles PDF, DOCX, PPTX, HTML, images, and other rich document formats.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from .schema import ParsedChunk, ParsedDocument


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
        self._max_tokens = max_tokens

        # Lazily initialised on first call to ``parse``.
        self._converter: object | None = None
        self._chunker: object | None = None

    # -- lazy init --------------------------------------------------------

    def _ensure_converter(self) -> None:
        """Build the Docling converter & chunker once, then reuse."""
        if self._converter is not None:
            return

        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pipeline_opts = PdfPipelineOptions()
        pipeline_opts.do_ocr = self._ocr
        pipeline_opts.do_table_structure = self._table_structure

        self._converter = DocumentConverter(
            format_options={
                "pdf": PdfFormatOption(pipeline_options=pipeline_opts),
            }
        )

        from docling_core.transforms.chunker import HierarchicalChunker

        self._chunker = HierarchicalChunker(
            max_tokens=self._max_tokens,
            include_metadata=True,
        )

    # -- public API -------------------------------------------------------

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse *file_path* and return a ``ParsedDocument``."""
        self._ensure_converter()
        assert self._converter is not None  # for type-checkers
        assert self._chunker is not None

        try:
            result = self._converter.convert(str(file_path))  # type: ignore[union-attr]
            doc = result.document

            raw_chunks = list(self._chunker.chunk(doc))  # type: ignore[union-attr]

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
                if meta.get("headings"):
                    prefix = " > ".join(str(h) for h in meta["headings"])  # type: ignore[union-attr]
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
