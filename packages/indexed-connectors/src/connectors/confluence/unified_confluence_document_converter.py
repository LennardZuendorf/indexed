"""Unified Confluence document converter supporting both Cloud and Server/DC.

Consolidates the previously separate ConfluenceDocumentConverter and
ConfluenceCloudDocumentConverter into a single parameterized implementation.

The only difference between Cloud and Server is dict nesting:
- Server: document["page"]["id"]
- Cloud:  document["page"]["content"]["id"]

This converter handles both via a _get_page() helper and uses ParsingModule
for intelligent chunking instead of RecursiveCharacterTextSplitter.
"""

from __future__ import annotations

import os
from typing import Any

from bs4 import BeautifulSoup
from loguru import logger


class UnifiedConfluenceDocumentConverter:
    """Unified converter for Confluence Cloud and Server/DC documents.

    Replaces separate ConfluenceDocumentConverter and ConfluenceCloudDocumentConverter
    with a single implementation parameterized by ``is_cloud``.

    Uses ParsingModule (lazy-loaded) for intelligent chunking of page body text
    and attachment parsing (OCR for images, AST for code, etc.).

    Args:
        is_cloud: True for Cloud API format, False for Server/DC.
        max_chunk_tokens: Maximum tokens per chunk (passed to ParsingModule).
        ocr: Enable OCR for image attachments.
        include_attachments: Whether to parse attachment bytes from the document.
    """

    def __init__(
        self,
        *,
        is_cloud: bool = False,
        max_chunk_tokens: int = 512,
        ocr: bool = True,
        include_attachments: bool = False,
    ) -> None:
        self._is_cloud = is_cloud
        self._max_chunk_tokens = max_chunk_tokens
        self._ocr = ocr
        self._include_attachments = include_attachments
        self._parsing: Any = None  # lazy ParsingModule

    @property
    def _parser(self) -> Any:
        """Lazy-load ParsingModule to avoid heavy imports at module level."""
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
        """Convert a Confluence document to indexed format.

        Args:
            document: Dict with "page" (and optionally "comments", "attachments").

        Returns:
            Single-element list with id, url, modifiedTime, text, chunks.
        """
        page = self._get_page(document)

        return [
            {
                "id": page["id"],
                "url": self._build_url(page),
                "modifiedTime": page["version"]["when"],
                "text": self._build_document_text(document),
                "chunks": self._split_to_chunks(document),
            }
        ]

    # ------------------------------------------------------------------
    # Page dict access (Cloud vs Server)
    # ------------------------------------------------------------------

    def _get_page(self, document: dict) -> dict:
        """Return the page dict regardless of Cloud/Server nesting."""
        if self._is_cloud:
            return document["page"]["content"]
        return document["page"]

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    def _build_document_text(self, document: dict) -> str:
        page = self._get_page(document)
        title = self._build_path_of_titles(page)
        body_and_comments = self._fetch_body_and_comments(document)
        return self._join_text([title, body_and_comments])

    def _fetch_body_and_comments(self, document: dict) -> str:
        page = self._get_page(document)
        body = self._get_cleaned_body(page)
        comments = [
            self._get_cleaned_body(comment) for comment in document.get("comments", [])
        ]
        return self._join_text([body] + comments)

    @staticmethod
    def _get_cleaned_body(node: dict) -> str:
        html = node.get("body", {}).get("storage", {}).get("value", "")
        if not html:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator=os.linesep, strip=True)

    @staticmethod
    def _build_path_of_titles(page: dict) -> str:
        page_title = [page["title"]] if "title" in page else []
        return " -> ".join(
            [
                ancestor["title"]
                for ancestor in page.get("ancestors", [])
                if "title" in ancestor
            ]
            + page_title
        )

    @staticmethod
    def _build_url(page: dict) -> str:
        base_url = page["_links"]["self"].split("/rest/api/")[0]
        return f"{base_url}{page['_links']['webui']}"

    @staticmethod
    def _join_text(elements: list[str], delimiter: str = "\n\n") -> str:
        return delimiter.join([e for e in elements if e])

    # ------------------------------------------------------------------
    # Chunking via ParsingModule
    # ------------------------------------------------------------------

    def _split_to_chunks(self, document: dict) -> list[dict]:
        page = self._get_page(document)

        # First chunk: title hierarchy (Confluence-specific context)
        chunks: list[dict] = [{"indexedData": self._build_path_of_titles(page)}]

        # Chunk body + comments via ParsingModule
        body_and_comments = self._fetch_body_and_comments(document)
        if body_and_comments:
            parsed = self._parser.parse_bytes(
                body_and_comments.encode("utf-8"), "page.md"
            )
            for chunk in parsed.chunks:
                entry: dict = {"indexedData": chunk.contextualized_text}
                if chunk.metadata:
                    entry["metadata"] = dict(chunk.metadata)
                chunks.append(entry)

        # Chunk attachments if present
        if self._include_attachments:
            chunks.extend(self._parse_attachments(document))

        return chunks

    def _parse_attachments(self, document: dict) -> list[dict]:
        """Parse attachment bytes via ParsingModule."""
        attachment_chunks: list[dict] = []
        attachments = document.get("attachments", [])

        for att in attachments:
            filename = att.get("filename", "unknown")
            data = att.get("bytes")
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
                logger.warning(f"Failed to parse attachment: {filename}")

        return attachment_chunks
