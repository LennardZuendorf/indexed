"""From the identifier under the cursor to the chunks that define it.

One resolver, two LSP methods: ``textDocument/definition`` today and
``textDocument/references`` next. Both start from the same three facts — the
cursor's identifier, the ONE collection whose source root owns the file, and one
keyed engine search — so the two cannot drift into different notions of "where a
symbol lives".

Two honesty rules from issue #241 live here, not at the call sites:

* a hit's position comes from ``indexed.utils.provenance.build_locator``, the
  same normaliser behind the CLI/MCP payload, so a source that knows only
  ``page``/``headings``/``document`` is never upgraded to a line range;
* a source with no line span degrades to the WHOLE DOCUMENT, measured from the
  file itself, and a source whose document text is not available (a remote Jira
  or Confluence page) yields no location at all. The ``0,0`` range
  ``results.lsp_range`` gives a span-less chunk is fine for a symbol list — it
  is not fine here, because a definition must not point at text the index never
  read.

Known limit, stated rather than hidden: the index holds chunks, not a symbol
table. A "definition" is a chunk that literally contains the identifier and is
the engine's top match for it, so a use site can outrank a declaration. The
alternative — inventing a declaration — is worse.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Set

from indexed.utils.provenance import build_locator

from .backend import KnowledgeBackend
from .results import document_uri, hit_text, is_path_chunk, lsp_range, uri_to_path

#: One tokenizer for hover and definition: what an identifier looks like here.
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: Locations one definition may return. A "go to definition" list is a
#: shortlist, and every fallback location costs one document read.
DEFINITION_LIMIT = 5

#: Search bound for one request: one collection, keyed by the owning manifest.
#: A keystroke must never enumerate the store.
DEFINITION_MAX_DOCS = 5
DEFINITION_MAX_CHUNKS = 15

Location = Dict[str, Any]
Range = Dict[str, Dict[str, int]]


def source_line(path: str, line: int) -> Optional[str]:
    """The ``line``th line of ``path`` (0-based), read only as far as needed."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for number, text in enumerate(handle):
                if number == line:
                    return text.rstrip("\n")
    except OSError:
        return None
    return None


def word_at(text: str, character: int) -> Optional[str]:
    """The identifier the cursor sits on (or just after), if any.

    Forgiving on purpose: hover must say *something* about the line the user is
    looking at, so a cursor in punctuation, indentation or whitespace still gets
    the nearest preceding word. Definition uses ``identifier_at`` instead.
    """
    best: Optional[str] = None
    for match in IDENTIFIER.finditer(text):
        if match.start() <= character <= match.end():
            return match.group(0)
        if match.end() <= character:
            best = match.group(0)
    return best


def identifier_at(path: str, position: Dict[str, Any]) -> Optional[str]:
    """The identifier exactly under the cursor, or ``None``.

    No fallbacks, unlike ``word_at``: a definition must name the thing the
    cursor is on. Guessing the file stem or the line's first word would answer a
    question the user did not ask.
    """
    line = position.get("line")
    character = position.get("character")
    if not isinstance(line, int) or isinstance(line, bool) or line < 0:
        return None
    if not isinstance(character, int) or isinstance(character, bool) or character < 0:
        return None
    text = source_line(path, line)
    if text is None:
        return None
    for match in IDENTIFIER.finditer(text):
        if match.start() <= character <= match.end():
            return match.group(0)
    return None


def document_range(path: str) -> Optional[Range]:
    """A range covering the whole document at ``path``, measured from the file.

    Used where the index knows which document a hit is in but not where in it:
    jumping to the top of a real document is honest, and the end position is the
    file's own (exclusive) end, not a guess. ``None`` when the file cannot be
    read — a caller must then emit no location rather than a fake one.
    """
    start = {"line": 0, "character": 0}
    lines = 0
    last = ""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for last in handle:
                lines += 1
    except OSError:
        return None
    if lines == 0:
        return {"start": start, "end": dict(start)}
    if last.endswith("\n"):
        return {"start": start, "end": {"line": lines, "character": 0}}
    return {"start": start, "end": {"line": lines - 1, "character": len(last)}}


def _range(
    text: str, metadata: Dict[str, Any], doc: Dict[str, Any], uri: str
) -> Optional[Range]:
    """The hit's range through the shared locator; ``None`` if unmappable."""
    locator = build_locator(metadata, str(doc.get("url") or ""))
    if locator["kind"] == "line_span":
        return lsp_range(text, metadata)
    target = uri_to_path(uri)
    return document_range(target) if target else None


def _position(
    text: str,
    metadata: Dict[str, Any],
    doc: Dict[str, Any],
    base_path: Optional[str],
) -> Optional[Location]:
    """One hit as an LSP ``Location``, or ``None`` when no honest one exists."""
    if is_path_chunk(text, metadata, doc):
        return None
    uri = document_uri(doc, metadata, base_path=base_path)
    if not uri:
        return None
    span = _range(text, metadata, doc, uri)
    if span is None:
        # No document text to measure: no location beats an invented one.
        return None
    return {"uri": uri, "range": span}


def chunk_location(
    doc: Dict[str, Any], hit: Dict[str, Any], *, base_path: Optional[str] = None
) -> Optional[Location]:
    """One matched chunk as a ``Location`` (``references`` builds on this)."""
    text, metadata = hit_text(hit)
    return _position(text, metadata, doc, base_path)


def _contains(text: str, word: str) -> bool:
    """True when ``word`` appears as a whole token — not inside ``alphabet``."""
    return any(match.group(0) == word for match in IDENTIFIER.finditer(text))


def matching_locations(
    results: Dict[str, Any],
    word: str,
    *,
    base_path_for: Optional[Callable[[str], Optional[str]]] = None,
    limit: int = DEFINITION_LIMIT,
) -> List[Location]:
    """The hits that really contain ``word``, as deduplicated locations.

    Engine order is kept: the index ranks by meaning, and re-ranking here would
    invent a symbol model it does not have. A hit is kept only if the identifier
    appears as a whole token in its text, because a range pointing at a chunk
    that never mentions the word is not a definition of it.
    """
    locations: List[Location] = []
    seen: Set[tuple[Any, ...]] = set()
    for collection, payload in results.items():
        if not isinstance(payload, dict) or "error" in payload:
            continue
        base_path = base_path_for(collection) if base_path_for else None
        for doc in payload.get("results") or []:
            if not isinstance(doc, dict):
                continue
            for hit in doc.get("matchedChunks") or []:
                text, metadata = hit_text(hit)
                if not _contains(text, word):
                    continue
                location = _position(text, metadata, doc, base_path)
                if location is None:
                    continue
                span = location["range"]
                key = (
                    location["uri"],
                    span["start"]["line"],
                    span["start"]["character"],
                    span["end"]["line"],
                    span["end"]["character"],
                )
                if key in seen:
                    continue
                seen.add(key)
                locations.append(location)
                if len(locations) >= limit:
                    return locations
    return locations


def resolve_definitions(
    backend: KnowledgeBackend,
    uri: str,
    position: Dict[str, Any],
    *,
    limit: int = DEFINITION_LIMIT,
) -> List[Location]:
    """Definitions for the identifier under a document position.

    Empty for anything the server cannot answer honestly: a non-file URI (no
    local text to take the cursor's word from), a cursor that is not on an
    identifier, a file no collection owns, or an index with no matching chunk.
    """
    path = uri_to_path(uri)
    if not path:
        return []
    word = identifier_at(path, position)
    if not word:
        return []
    status = backend.collection_for_path(path)
    if status is None:
        return []
    collection = getattr(status, "name", "")
    results = backend.search(
        word,
        collection,
        max_docs=DEFINITION_MAX_DOCS,
        max_chunks=DEFINITION_MAX_CHUNKS,
    )
    return matching_locations(
        results, word, base_path_for=backend.base_path, limit=limit
    )


__all__ = [
    "DEFINITION_LIMIT",
    "DEFINITION_MAX_CHUNKS",
    "DEFINITION_MAX_DOCS",
    "IDENTIFIER",
    "chunk_location",
    "document_range",
    "identifier_at",
    "matching_locations",
    "resolve_definitions",
    "source_line",
    "word_at",
]
