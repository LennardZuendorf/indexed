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

    def _fallback_chunks(self, text: str) -> list[str]:
        """Split raw text into parser-sized pieces when the parser cannot.

        The parser is the only component that normally bounds a chunk. If it
        raises or yields nothing, the raw body must still not become one
        unbounded hit (#340 R5): fall back to a hard window derived from the
        same token budget (4 characters per token, the estimate the parsers
        use), split after whitespace where one is available. No character is
        dropped, so a fallback chunk never hides comment text.
        """
        max_chars = max(self._max_chunk_tokens * 4, 1)
        if len(text) <= max_chars:
            return [text]
        pieces: list[str] = []
        remaining = text
        while len(remaining) > max_chars:
            cut = remaining.rfind("\n", 0, max_chars)
            if cut <= 0:
                cut = remaining.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            else:
                cut += 1  # keep the separator with the left piece
            pieces.append(remaining[:cut])
            remaining = remaining[cut:]
        if remaining:
            pieces.append(remaining)
        return pieces

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
            return [
                {"indexedData": piece, "metadata": dict(src_meta)}
                for piece in self._fallback_chunks(body)
            ]
        if not parsed.chunks:
            # No chunks is a parser failure, not an empty body: dropping the
            # body here would index the title and call the document complete.
            logger.warning(
                "GitHub body for %s parsed to no chunks; using raw text",
                document["id"],
            )
            return [
                {"indexedData": piece, "metadata": dict(src_meta)}
                for piece in self._fallback_chunks(body)
            ]
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
            meta = {**src_meta, "commentAuthor": author}
            # The comment's own address, so a hit can be cited as the comment
            # rather than as "somewhere in this issue" (#340 R1).
            if comment.get("id"):
                meta["commentId"] = comment["id"]
            if comment.get("url"):
                meta["commentUrl"] = comment["url"]
            text = f"Comment by {author}:\n\n{body}"
            # Bounded by the same 512-token chunker as an issue body: one long
            # comment must not become one unbounded hit (#340 R5).
            try:
                parsed = self._parser.parse_bytes(text.encode("utf-8"), "content.md")
            except Exception:
                logger.warning(
                    "Failed to parse GitHub comment on %s; using raw text",
                    document["id"],
                )
                chunks.extend(
                    {"indexedData": piece, "metadata": dict(meta)}
                    for piece in self._fallback_chunks(text)
                )
                continue
            if not parsed.chunks:
                logger.warning(
                    "GitHub comment on %s parsed to no chunks; using raw text",
                    document["id"],
                )
                chunks.extend(
                    {"indexedData": piece, "metadata": dict(meta)}
                    for piece in self._fallback_chunks(text)
                )
                continue
            chunks.extend(
                {
                    "indexedData": chunk.contextualized_text,
                    "metadata": {**meta, **chunk.metadata},
                }
                for chunk in parsed.chunks
            )
        return chunks
