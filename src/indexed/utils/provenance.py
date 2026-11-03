"""Where a hit sits — one normaliser for every surface.

The ``indexed.search/1`` contract (``indexed.protocols.results``) lets a locator
state only what the index actually knows about a hit's position: a 1-based
inclusive line span for code, a page for paginated documents, a heading path for
prose, or nothing at all. The CLI/MCP payload builder and the LSP server both
answer from it, so the conversion lives here instead of being mirrored in two
presentation modules that can silently drift apart.

Leaf-layer on purpose: imports ``indexed.protocols`` only, so every consumer —
including the top-layer presentation surfaces — may use it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from indexed.protocols.results import Locator


def build_locator(metadata: Optional[Dict[str, Any]], doc_url: str) -> Locator:
    """Say where a hit sits — and say nothing it does not know.

    Precision order: a line span outranks a page, which outranks a heading
    path, which outranks the bare document. Sources differ: tree-sitter code
    chunks carry ``start_line``/``end_line`` (0-based, inclusive) and a
    ``file_path``; Docling-parsed PDFs/DOCX carry ``page``; Markdown, Jira,
    Confluence and Outline carry ``headings`` only. A source with none of
    them gets ``kind: "document"`` rather than an invented range.
    """
    meta = metadata or {}

    path = meta.get("file_path") or _path_from_url(doc_url)
    start, end = meta.get("start_line"), meta.get("end_line")
    if isinstance(start, int) and isinstance(end, int) and path:
        # 0-based inclusive on disk -> 1-based inclusive here: what `grep -n`
        # prints and what every editor shows.
        return {
            "kind": "line_span",
            "path": path,
            "start_line": start + 1,
            "end_line": end + 1,
        }

    page = meta.get("page")
    if isinstance(page, int) and page > 0:
        locator: Locator = {"kind": "page", "page": page}
        if path:
            locator["path"] = path
        return locator

    headings = meta.get("headings")
    if isinstance(headings, list):
        # Decide the kind AFTER cleaning: the Markdown/Jira converters emit
        # ``headings: [""]`` for whole-file chunks, and a ``headings`` locator
        # declaring an empty path would claim a precision the chunk does not
        # have. An empty cleaning means "position unknown" -> ``document``.
        cleaned = [h.strip() for h in headings if isinstance(h, str) and h.strip()]
        if cleaned:
            return {"kind": "headings", "headings": cleaned}

    return {"kind": "document"}


def chunk_parts(chunk_data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Pull ``(text, metadata)`` out of a matched chunk's ``content``.

    v1 puts the raw converted chunk there (``{indexedData, metadata}``); v2
    used to put ``{indexedData}`` only, so v2 hits lost their locator — both
    engines now carry ``metadata`` when the chunk has any. A plain string
    ``content`` is text with no metadata; dropping it would hide a real hit.
    """
    content = chunk_data.get("content")
    if isinstance(content, str):
        return content, {}
    if not isinstance(content, dict):
        return "", {}
    metadata = content.get("metadata")
    text = content.get("indexedData") or ""
    if not isinstance(text, str):
        text = str(text)
    return text, metadata if isinstance(metadata, dict) else {}


def strip_context_prefix(text: str, metadata: Dict[str, Any]) -> str:
    """Drop the context prefix a chunk embeds in its text.

    The indexer prepends the file path so the embedding sees it, in two shapes:
    code chunks use ``# <path>\\n`` (tree-sitter), plaintext chunks the bare
    ``<path>\\n`` (``parsing/plaintext_parser.py``). The payload already carries
    that path in ``locator.path``, so a hit must not start with a line the
    reader has to strip — and a symbol name must not BE that line.
    """
    path = metadata.get("file_path")
    if isinstance(path, str) and path:
        for prefix in (f"# {path}\n", f"{path}\n"):
            if text.startswith(prefix):
                return text[len(prefix) :]
    return text


def _path_from_url(url: str) -> str:
    """``file:///a/b.py`` -> ``/a/b.py``; anything else is left alone."""
    if url.startswith("file://"):
        return url[len("file://") :]
    return ""


__all__ = ["build_locator", "chunk_parts", "strip_context_prefix"]
