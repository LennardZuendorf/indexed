"""Unified Jira document converter supporting both Cloud and Server/DC instances.

Handles both Cloud (ADF format) and Server (plain text/HTML) automatically.
Uses ParsingModule for intelligent chunking instead of RecursiveCharacterTextSplitter.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


class UnifiedJiraDocumentConverter:
    """Unified converter for Jira Cloud and Server/DC documents.

    Automatically detects ADF (Cloud) vs plain text (Server) content and
    uses ParsingModule for chunking.

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
        include_attachments: bool = False,
        # Legacy params (ignored, kept for backward compat)
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
    ) -> None:
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

    def convert(self, document: dict) -> list[dict]:
        """Convert a Jira document to indexed format.

        Args:
            document: Jira issue document as dictionary.

        Returns:
            Single-element list with id, url, modifiedTime, text, chunks.
        """
        return [
            {
                "id": document["key"],
                "url": self._build_url(document),
                "modifiedTime": document["fields"]["updated"],
                "text": self._build_document_text(document),
                "chunks": self._split_to_chunks(document),
            }
        ]

    # ------------------------------------------------------------------
    # Text building (unchanged logic)
    # ------------------------------------------------------------------

    def _build_document_text(self, document: dict) -> str:
        main_info = self._build_main_ticket_info(document)
        description_and_comments = self._fetch_description_and_comments(document)
        return self._join_text([main_info, description_and_comments])

    def _fetch_description_and_comments(self, document: dict) -> str:
        description = self._fetch_description(document)
        comments = self._fetch_comments(document)
        return self._join_text([description] + comments).strip()

    def _fetch_description(self, document: dict) -> str:
        description = document.get("fields", {}).get("description")
        if not description:
            return ""
        if isinstance(description, dict):
            return self._parse_adf_content(description)
        return str(description) if description else ""

    def _fetch_comments(self, document: dict) -> list[str]:
        comments_data = (
            document.get("fields", {}).get("comment", {}).get("comments", [])
        )
        comments: list[str] = []
        for comment in comments_data:
            body = comment.get("body")
            if not body:
                continue
            if isinstance(body, dict):
                parsed = self._parse_adf_content(body)
            else:
                parsed = str(body) if body else ""
            if parsed:
                comments.append(parsed)
        return comments

    # ------------------------------------------------------------------
    # ADF parsing (Jira Cloud specific)
    # ------------------------------------------------------------------

    def _parse_adf_content(self, adf_doc: dict) -> str:
        if not adf_doc or not isinstance(adf_doc, dict):
            return ""
        content = adf_doc.get("content", [])
        return self._parse_adf_nodes(content)

    def _parse_adf_nodes(
        self, nodes: list, depth: int = 0, block_level: bool = True
    ) -> str:
        texts: list[str] = []
        for node in nodes or []:
            node_type = node.get("type")

            if node_type == "paragraph":
                para_text = self._parse_adf_nodes(
                    node.get("content", []), depth, block_level=False
                )
                if para_text:
                    texts.append(para_text)

            elif node_type == "heading":
                heading_text = self._parse_adf_nodes(
                    node.get("content", []), depth, block_level=False
                )
                if heading_text:
                    level = node.get("attrs", {}).get("level", 1)
                    texts.append(f"{'#' * int(level)} {heading_text}")

            elif node_type in ("bulletList", "orderedList"):
                list_items = self._parse_adf_nodes(
                    node.get("content", []), depth + 1, block_level=True
                )
                if list_items:
                    texts.append(list_items)

            elif node_type == "listItem":
                item_text = self._parse_adf_nodes(
                    node.get("content", []), depth, block_level=False
                )
                if item_text:
                    indent = "  " * depth
                    texts.append(f"{indent}- {item_text}")

            elif node_type == "codeBlock":
                code_text = self._parse_adf_nodes(
                    node.get("content", []), depth, block_level=False
                )
                if code_text:
                    texts.append(f"```\n{code_text}\n```")

            elif node_type == "text":
                text_content = node.get("text", "")
                for mark in node.get("marks", []) or []:
                    mark_type = mark.get("type")
                    if mark_type == "strong":
                        text_content = f"**{text_content}**"
                    elif mark_type == "em":
                        text_content = f"*{text_content}*"
                    elif mark_type == "code":
                        text_content = f"`{text_content}`"
                texts.append(text_content)

            elif node_type == "hardBreak":
                texts.append("\n")

            elif "content" in node:
                nested = self._parse_adf_nodes(
                    node.get("content", []), depth, block_level
                )
                if nested:
                    texts.append(nested)

        if not block_level or depth > 0:
            return "".join(texts)
        return "\n\n".join(filter(None, texts))

    # ------------------------------------------------------------------
    # Chunking via ParsingModule
    # ------------------------------------------------------------------

    def _split_to_chunks(self, document: dict) -> list[dict]:
        # First chunk: ticket key + summary (Jira-specific context)
        chunks: list[dict] = [{"indexedData": self._build_main_ticket_info(document)}]

        # Chunk description + comments via ParsingModule
        description_and_comments = self._fetch_description_and_comments(document)
        if description_and_comments:
            parsed = self._parser.parse_bytes(
                description_and_comments.encode("utf-8"), "content.md"
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_main_ticket_info(document: dict) -> str:
        return f"{document['key']} : {document['fields']['summary']}"

    @staticmethod
    def _join_text(elements: list[str], delimiter: str = "\n\n") -> str:
        return delimiter.join([e for e in elements if e]).strip()

    @staticmethod
    def _build_url(document: dict) -> str:
        base_url = document["self"].split("/rest/api/")[0]
        return f"{base_url}/browse/{document['key']}"
