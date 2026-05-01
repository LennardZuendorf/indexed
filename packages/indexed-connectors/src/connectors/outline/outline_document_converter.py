"""Outline Wiki document converter.

Converts Outline documents (Markdown) into indexed chunks via ParsingModule.
Mirrors UnifiedConfluenceDocumentConverter but operates on Markdown directly —
no BeautifulSoup HTML stripping needed since Outline bodies are already Markdown.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


class OutlineDocumentConverter:
    """Convert Outline documents to indexed chunk format.

    Args:
        max_chunk_tokens: Maximum tokens per chunk (passed to ParsingModule).
        ocr: Enable OCR for image attachments.
        include_attachments: Whether to parse attachment bytes from the document.
    """

    def __init__(
        self,
        *,
        max_chunk_tokens: int = 512,
        ocr: bool = True,
        include_attachments: bool = True,
    ) -> None:
        self._max_chunk_tokens = max_chunk_tokens
        self._ocr = ocr
        self._include_attachments = include_attachments
        self._parsing: Any = None

    @property
    def _parser(self) -> Any:
        """Lazy-load ParsingModule to keep CLI startup fast."""
        if self._parsing is None:
            from parsing import ParsingModule

            self._parsing = ParsingModule(
                ocr=self._ocr,
                table_structure=True,
                max_tokens=self._max_chunk_tokens,
            )
        return self._parsing

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self, document: dict) -> list[dict]:
        """Convert an Outline document dict to indexed format.

        Args:
            document: Dict with "document" (full Outline API doc dict) and
                      "attachments" (list of downloaded attachment dicts).

        Returns:
            Single-element list with id, url, modifiedTime, text, chunks.
        """
        doc = document["document"]

        return [
            {
                "id": doc["id"],
                "url": self._build_url(doc),
                "modifiedTime": doc.get("updatedAt", ""),
                "text": self._build_full_text(document),
                "chunks": self._split_to_chunks(document),
            }
        ]

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    def _build_full_text(self, document: dict) -> str:
        doc = document["document"]
        title_path = self._build_title_path(doc)
        body = doc.get("text", "")
        parts = [p for p in [title_path, body] if p]
        return "\n\n".join(parts)

    @staticmethod
    def _build_title_path(doc: dict) -> str:
        """Build a breadcrumb title path using the document title."""
        # Outline's documents.info does not return ancestor titles —
        # use collectionId and title directly for now.
        # A full ancestor walk requires a pre-built title map; that
        # optimisation is deferred to a follow-up.
        return str(doc.get("title", ""))

    @staticmethod
    def _build_url(doc: dict) -> str:
        """Return the public URL for the document."""
        return str(doc.get("url", ""))

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _split_to_chunks(self, document: dict) -> list[dict]:
        doc = document["document"]

        # First chunk: title (gives search context)
        title_path = self._build_title_path(doc)
        chunks: list[dict] = [{"indexedData": title_path}] if title_path else []

        # Chunk body via ParsingModule
        body = doc.get("text", "")
        if body:
            try:
                parsed = self._parser.parse_bytes(body.encode("utf-8"), "doc.md")
                for chunk in parsed.chunks:
                    entry: dict = {"indexedData": chunk.contextualized_text}
                    if chunk.metadata:
                        entry["metadata"] = dict(chunk.metadata)
                    chunks.append(entry)
            except Exception as exc:
                logger.warning(
                    "Failed to parse body of doc {}: {}", doc.get("id", "?"), exc
                )
                chunks.append({"indexedData": body})

        # Chunk attachments if enabled
        if self._include_attachments:
            chunks.extend(self._parse_attachments(document))

        return chunks

    def _parse_attachments(self, document: dict) -> list[dict]:
        """Parse attachment bytes via ParsingModule."""
        attachment_chunks: list[dict] = []
        attachments = document.get("attachments", [])

        for att in attachments:
            filename = att.get("filename", "unknown")
            data: bytes = att.get("bytes", b"")
            if not data:
                continue

            try:
                parsed = self._parser.parse_bytes(data, filename)
                for chunk in parsed.chunks:
                    entry: dict = {"indexedData": chunk.contextualized_text}
                    meta = dict(chunk.metadata) if chunk.metadata else {}
                    meta["attachment"] = filename
                    entry["metadata"] = meta
                    attachment_chunks.append(entry)
            except Exception:
                logger.warning("Failed to parse attachment: {}", filename)

        return attachment_chunks
