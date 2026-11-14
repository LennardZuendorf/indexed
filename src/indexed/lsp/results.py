"""Turn core search results into LSP symbols and hover markdown.

The provenance vocabulary is the ``indexed.search/1`` contract
(``indexed.protocols.results``): a locator says only what the index actually
knows about a hit's position — a 1-based inclusive line span for code, a page
for paginated documents, a heading path for prose, or nothing at all. The
normaliser and the chunk accessors are shared with the CLI/MCP payload builder
(``indexed.utils.provenance``), so the LSP cannot drift into a third shape.
LSP speaks 0-based lines, so that conversion happens here and nowhere else.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import unquote

from indexed.protocols.results import Locator
from indexed.utils.provenance import build_locator, chunk_parts, strip_context_prefix
from indexed.utils.relevance import V1_SCORE_KIND, unified_relevance

# SymbolKind values from the LSP specification (3.17).
SK_FILE = 1
SK_NAMESPACE = 3
SK_CLASS = 5
SK_FUNCTION = 12
SK_STRUCT = 23

#: Hover text longer than this is truncated — a hover popup is a glance, not a
#: reader. Matches the "one chunk is enough" intent of the Tier 0 scope.
MAX_HOVER_CHARS = 1200

#: Symbol names come from a chunk's own first line, so they are bounded too.
MAX_SYMBOL_NAME = 80


# -- chunk access -------------------------------------------------------------


def hit_text(hit: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """The hit's renderable text and metadata, without the embedder's prefix."""
    text, metadata = chunk_parts(hit)
    return strip_context_prefix(text, metadata), metadata


def is_path_chunk(text: str, metadata: Dict[str, Any], doc: Dict[str, Any]) -> bool:
    """True for the chunk-0 path stub every v1 document carries.

    It states the document's relative path and nothing else; emitting it as a
    symbol would flood the palette with position-less entries.
    """
    if metadata:
        return False
    stripped = text.strip()
    if not stripped:
        return True
    return stripped in {str(doc.get("id") or ""), str(doc.get("title") or "")}


# -- locators and URIs --------------------------------------------------------


def uri_to_path(uri: str) -> Optional[str]:
    """``file:///a/b.py`` -> ``/a/b.py``; ``None`` for non-file URIs.

    Connectors build ``file://{abs_path}`` verbatim, so the remainder is often
    a real path — spaces, non-ASCII and all — while a URI from an editor is
    percent-encoded. Try the literal path first and only fall back to the
    unquoted form, so a filename that legitimately contains ``%`` keeps
    working.
    """
    if not uri.startswith("file://"):
        return None
    raw = uri[len("file://") :]
    if os.path.exists(raw):
        return raw
    return unquote(raw)


def _file_uri(path: str, base_path: Optional[str] = None) -> str:
    """A percent-encoded ``file://`` URI for *path*.

    ``Path.as_uri`` is what makes it a URI at all: strict clients (Helix's
    ``url::Url``) reject the raw ``file:///my corpus ü/a b.py`` a hand-built
    url produces. A relative path resolves against the collection's
    ``base_path`` — never the server process's cwd, which belongs to the
    editor, not to the collection.
    """
    if not os.path.isabs(path):
        path = os.path.join(base_path, path) if base_path else os.path.abspath(path)
    return Path(path).as_uri()


def document_uri(
    doc: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
    *,
    base_path: Optional[str] = None,
) -> str:
    """The best real URI for a hit's file: the document's own url, else the file."""
    url = doc.get("url")
    if isinstance(url, str) and url.startswith("file://"):
        # Re-emit the connector's own file url percent-encoded: it is built by
        # string concatenation upstream and is not a URI until it is encoded.
        path = uri_to_path(url)
        return _file_uri(path) if path else ""
    if isinstance(url, str) and "://" in url:
        return url
    meta = metadata or {}
    path = meta.get("file_path")
    if isinstance(path, str) and path:
        return _file_uri(path, base_path)
    if isinstance(url, str) and url:
        return url
    return ""


def lsp_range(text: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """A 0-based LSP range from the chunk's 0-based inclusive line metadata.

    The end character is the length of the chunk's own last line: that is the
    indexed extent, so a file edited since the index was built cannot stretch
    the range over content the hit never covered.
    """
    start, end = metadata.get("start_line"), metadata.get("end_line")
    if (
        isinstance(start, int)
        and isinstance(end, int)
        and not isinstance(start, bool)
        and not isinstance(end, bool)
        and start >= 0
        and end >= start
    ):
        lines = text.splitlines()
        last_line = lines[-1] if lines else ""
        return {
            "start": {"line": start, "character": 0},
            "end": {"line": end, "character": len(last_line)},
        }
    zero = {"line": 0, "character": 0}
    return {"start": dict(zero), "end": dict(zero)}


# -- symbols -----------------------------------------------------------------


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _symbol_name(text: str, locator: Locator, doc: Dict[str, Any]) -> str:
    if locator["kind"] == "headings":
        headings = locator.get("headings") or []
        if headings:
            return str(headings[-1])[:MAX_SYMBOL_NAME]
    first = _first_line(text)
    if first:
        return first[:MAX_SYMBOL_NAME]
    fallback = locator.get("path") or str(doc.get("id") or "document")
    return os.path.basename(str(fallback))


def _symbol_kind(locator: Locator, metadata: Dict[str, Any]) -> int:
    if locator["kind"] == "headings":
        return SK_NAMESPACE
    node = str(metadata.get("node_type") or "")
    if "function" in node or "method" in node:
        return SK_FUNCTION
    if "class" in node:
        return SK_CLASS
    if any(word in node for word in ("struct", "trait", "enum", "impl")):
        return SK_STRUCT
    # A span in a file is all that is known; call it what it is.
    return SK_FILE


def build_symbols(
    results: Dict[str, Any],
    *,
    limit: int = 50,
    base_path_for: Optional[Callable[[str], Optional[str]]] = None,
) -> List[Dict[str, Any]]:
    """LSP ``SymbolInformation`` entries for the hits of one search.

    Order is the engine's (most relevant first, per collection); duplicates
    (same file and span, reachable from two collections) keep the first.
    ``base_path_for`` supplies a collection's source root so a relative chunk
    ``file_path`` resolves to the right file URI, not the server's cwd.
    """
    symbols: List[Dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for collection, payload in results.items():
        if not isinstance(payload, dict) or "error" in payload:
            continue
        base_path = base_path_for(collection) if base_path_for else None
        for doc in payload.get("results") or []:
            if not isinstance(doc, dict):
                continue
            for hit in doc.get("matchedChunks") or []:
                text, metadata = hit_text(hit)
                if is_path_chunk(text, metadata, doc):
                    continue
                uri = document_uri(doc, metadata, base_path=base_path)
                if not uri:
                    continue
                locator = build_locator(metadata, str(doc.get("url") or ""))
                rng = lsp_range(text, metadata)
                key = (uri, rng["start"]["line"], rng["end"]["line"])
                if key in seen:
                    continue
                seen.add(key)
                symbols.append(
                    {
                        "name": _symbol_name(text, locator, doc),
                        "kind": _symbol_kind(locator, metadata),
                        "location": {"uri": uri, "range": rng},
                        "containerName": collection,
                    }
                )
                if len(symbols) >= limit:
                    return symbols
    return symbols


# -- hover -------------------------------------------------------------------


def _relative_age(timestamp: Optional[str], now: datetime) -> str:
    """A short, stable age string for a collection's index time.

    Deliberately not ``indexed.cli.utils.format.format_time``: that one reads
    the wall clock, and this value is part of a pinned golden payload.
    """
    if not timestamp:
        return "at an unknown time"
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return f"at {timestamp}"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    seconds = int((now - parsed).total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    return f"on {parsed.strftime('%Y-%m-%d')}"


def _locator_label(locator: Locator, doc: Dict[str, Any]) -> str:
    if locator["kind"] == "line_span":
        path = locator.get("path") or "document"
        return f"`{path}:{locator.get('start_line')}-{locator.get('end_line')}`"
    if locator["kind"] == "page":
        page = locator.get("page")
        path = locator.get("path")
        return f"`{path}` p.{page}" if path else f"page {page}"
    if locator["kind"] == "headings":
        return "`" + " > ".join(locator.get("headings") or []) + "`"
    return f"`{doc.get('id') or 'document'}`"


def _score_line(hit: Dict[str, Any], score_kind: str) -> str:
    """One comparable relevance first, the engine's raw score second.

    A raw L2 distance is *smaller* when the match is better, so printing it
    alone (or calling it "score") reads inverted. ``unified_relevance`` is the
    same mapping the CLI/MCP payload uses; the raw value stays visible next to
    its kind for anyone comparing within one engine.
    """
    score = hit.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return f"score kind {score_kind}"
    relevance = unified_relevance(float(score), score_kind)
    return f"relevance {relevance:.4f} · score {float(score):.4f} ({score_kind})"


def build_hover(
    results: Dict[str, Any],
    statuses: Dict[str, Any],
    query: str,
    *,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    """The hover card for the top hit: text, collection, source type, freshness.

    No ``range`` is emitted: LSP defines ``Hover.range`` in the *hovered*
    document, and the top hit may live in a different file, so a range here
    would underline unrelated text. The locator line states the real position.

    Returns ``None`` when the index has nothing to say, which LSP renders as an
    empty hover — never as invented content.
    """
    now = now or datetime.now(timezone.utc)
    for collection, payload in results.items():
        if not isinstance(payload, dict) or "error" in payload:
            continue
        for doc in payload.get("results") or []:
            if not isinstance(doc, dict):
                continue
            for hit in doc.get("matchedChunks") or []:
                text, metadata = hit_text(hit)
                if is_path_chunk(text, metadata, doc):
                    continue
                status = statuses.get(collection)
                source_type = getattr(status, "source_type", None) or "unknown"
                freshness = _relative_age(getattr(status, "updated_time", None), now)
                locator = build_locator(metadata, str(doc.get("url") or ""))
                score_kind = str(payload.get("scoreKind") or V1_SCORE_KIND)
                score_text = _score_line(hit, score_kind)
                body = text.strip()
                if len(body) > MAX_HOVER_CHARS:
                    body = body[:MAX_HOVER_CHARS].rstrip() + "\n… (truncated)"
                language = metadata.get("language")
                fence = f"```{language}" if isinstance(language, str) else "```"
                value = (
                    f"**indexed** · `{collection}` · {source_type} · "
                    f"indexed {freshness}\n\n"
                    f"{fence}\n{body}\n```\n\n"
                    f"{_locator_label(locator, doc)} · {score_text} · "
                    f"query `{query}`"
                )
                return {"contents": {"kind": "markdown", "value": value}}
    return None


__all__ = [
    "MAX_HOVER_CHARS",
    "build_hover",
    "build_symbols",
    "document_uri",
    "hit_text",
    "is_path_chunk",
    "lsp_range",
    "uri_to_path",
]
