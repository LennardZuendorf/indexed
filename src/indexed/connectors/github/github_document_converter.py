"""Converts GitHub raw documents (issues/PRs/draft items) into indexed chunks."""

from __future__ import annotations

import logging
from typing import Iterator

logger = logging.getLogger(__name__)


class GitHubDocumentConverter:
    def __init__(self, max_chunk_tokens: int = 512) -> None:
        self._max_chunk_tokens = max_chunk_tokens
        self._parser_instance = None

    @property
    def _parser(self):
        if self._parser_instance is None:
            from indexed.parsing import ParsingModule

            self._parser_instance = ParsingModule(max_tokens=self._max_chunk_tokens)
        return self._parser_instance

    def convert(self, document: dict) -> Iterator[dict]:
        src_meta = {
            "sourceId": document["id"],
            "sourceUrl": document["url"],
            "sourceUpdatedAt": document["modifiedTime"],
            "kind": document["kind"],
            "state": document["state"],
        }
        if document.get("project_fields"):
            src_meta["projectFields"] = document["project_fields"]

        chunks = [
            {"indexedData": self._build_header(document), "metadata": dict(src_meta)}
        ]
        chunks.extend(self._body_chunks(document, src_meta))
        chunks.extend(self._comment_chunks(document, src_meta))

        yield {
            "id": document["id"],
            "url": document["url"],
            "modifiedTime": document["modifiedTime"],
            "text": document.get("body") or document["title"],
            "chunks": chunks,
        }

    def _build_header(self, document: dict) -> str:
        labels = ", ".join(document.get("labels") or []) or "none"
        return (
            f"# {document['title']}\n\n"
            f"State: {document['state']} | Labels: {labels} | "
            f"Author: {document.get('author') or 'unknown'}"
        )

    def _body_chunks(self, document: dict, src_meta: dict) -> list[dict]:
        body = document.get("body") or ""
        if not body.strip():
            return []
        try:
            parsed = self._parser.parse_bytes(body.encode("utf-8"), "content.md")
        except Exception:
            logger.warning(
                "Failed to parse GitHub body for %s; using raw text", document["id"]
            )
            return [{"indexedData": body, "metadata": dict(src_meta)}]
        return [
            {
                "indexedData": chunk.contextualized_text,
                "metadata": {**src_meta, **chunk.metadata},
            }
            for chunk in parsed.chunks
        ]

    def _comment_chunks(self, document: dict, src_meta: dict) -> list[dict]:
        chunks = []
        for comment in document.get("comments") or []:
            body = comment.get("body") or ""
            if not body.strip():
                continue
            author = comment.get("author") or "unknown"
            text = f"Comment by {author}:\n\n{body}"
            chunks.append(
                {"indexedData": text, "metadata": {**src_meta, "commentAuthor": author}}
            )
        return chunks
