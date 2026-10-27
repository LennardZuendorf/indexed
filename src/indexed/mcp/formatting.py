"""The machine-readable search payload (``indexed.search/1``).

This is the ONE result shape for machine consumers: the MCP ``search`` /
``search_collection`` tools return it, and the CLI prints it byte-for-byte
under ``indexed search --json`` (``--simple-output`` is the legacy alias).
The contract is typed in ``indexed.protocols.results`` and documented for
users in ``.spec/tech-app.md`` § Search result contract (issues #108/#109).

Shape, in one breath: documents grouped, each stating its collection, source
type, id, url and score semantics ONCE; each hit carrying only its
relevance, raw score, locator and text.

Grouping was the point. The old flat payload repeated ``collection``,
``document_id`` and ``document_url`` on every chunk and said nothing about
WHERE the chunk sits — the two costs that made MCP output both bulky and
unactionable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from indexed.protocols.results import SEARCH_SCHEMA, Hit, Locator
from indexed.utils.relevance import unified_relevance

#: Score kind reported for a v1 collection, which carries no ``scoreKind``
#: key: squared-L2 distance over unit vectors (see ``unified_relevance``).
V1_SCORE_KIND = "l2_squared"

#: Precision of the emitted floats. Four decimals is well past the point a
#: ranking can change, and drops the ~17-digit tails that cost tokens per hit.
_SCORE_DECIMALS = 4


def build_search_payload(raw_results: Dict[str, Any], query: str) -> Dict[str, Any]:
    """Turn the core search result into the documented payload.

    ``raw_results`` maps collection name -> per-collection result, as returned
    by ``indexed.core.engine.search`` (v1 or v2). Each collection may carry
    ``error``, ``results`` and — from this schema on — ``sourceType`` and
    ``scoreKind``. Collections arrive already fetched with matched-chunk
    content (``include_matched_chunks=True``), because the locator and the
    text both live in a chunk's ``content``/``metadata``.
    """
    collection_errors: List[Dict[str, Any]] = []
    searched: List[str] = []
    # (collection, document key) -> document payload under construction.
    documents: Dict[Tuple[str, str], Dict[str, Any]] = {}
    # Flat ranking list; grouping happens after the sort, so a document's
    # position reflects its BEST hit (v1 `__build_results` semantics).
    ranked: List[Tuple[float, Tuple[str, str], Hit]] = []

    for collection_name, collection_data in raw_results.items():
        if isinstance(collection_data, dict) and "error" in collection_data:
            collection_errors.append(
                {"collection": collection_name, "error": collection_data["error"]}
            )
            continue

        if not isinstance(collection_data, dict):
            continue

        searched.append(collection_name)
        raw_score_kind = collection_data.get("scoreKind")
        # A collection is fed by exactly one reader, so its source type is a
        # document-level fact. Absent when the manifest does not say (a v1
        # collection built before the field existed) — never guessed.
        source_type = collection_data.get("sourceType")
        score_kind = raw_score_kind or V1_SCORE_KIND

        for doc in collection_data.get("results", []) or []:
            doc_id = str(doc.get("id", ""))
            doc_url = doc.get("url") or ""
            key = (collection_name, doc_id)
            if key not in documents:
                # Key order is the documented one (.spec/tech-app.md § Search
                # result contract): document facts first, hits last.
                entry: Dict[str, Any] = {"collection": collection_name}
                if source_type:
                    entry["source_type"] = source_type
                entry["id"] = doc_id
                if doc_url:
                    entry["url"] = doc_url
                entry["score_kind"] = score_kind
                entry["hits"] = []
                documents[key] = entry  # type: ignore[assignment]

            for chunk_data in doc.get("matchedChunks", []) or []:
                text, metadata = _chunk_parts(chunk_data)
                if not text:
                    continue
                raw_score = float(chunk_data.get("score", 0.0) or 0.0)
                locator = build_locator(metadata, doc_url)
                hit: Hit = {
                    "relevance": round(unified_relevance(raw_score, score_kind), 4),
                    "score": round(raw_score, _SCORE_DECIMALS),
                    "locator": locator,
                    "text": _strip_context_prefix(text, metadata),
                }
                ranked.append((hit["relevance"], key, hit))

    # Best first. Ties keep discovery order: sort is stable.
    ranked.sort(key=lambda item: item[0], reverse=True)
    ordered: List[Dict[str, Any]] = []
    admitted: set[Tuple[str, str]] = set()
    for _, key, hit in ranked:
        documents[key]["hits"].append(hit)
        # Documents appear in the order their BEST hit does.
        if key not in admitted:
            admitted.add(key)
            ordered.append(documents[key])

    documents_out = [_finalize_document(doc) for doc in ordered]

    return {
        "schema": SEARCH_SCHEMA,
        "query": query,
        "counts": {"documents": len(documents_out), "hits": len(ranked)},
        "collections": searched,
        "collection_errors": collection_errors,
        "documents": documents_out,
    }


def _finalize_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Hoist the repeated per-hit path/url onto the document, then reorder keys.

    A document's hits nearly always sit in the same file, so repeating an
    absolute path on every hit is exactly the boilerplate this shape exists to
    remove (it measured LARGER than the payload it replaced). The path is
    stated once on the document and stripped from the hits; a hit whose path
    genuinely differs keeps its own. Likewise a ``file://`` url that only
    restates the path carries no extra information and is dropped.
    """
    hits: List[Hit] = doc["hits"]
    paths = {h["locator"].get("path") for h in hits if h["locator"].get("path")}
    doc_path: Optional[str] = None
    if len(paths) == 1:
        doc_path = next(iter(paths))
        for hit in hits:
            hit["locator"].pop("path", None)

    out: Dict[str, Any] = {"collection": doc["collection"]}
    if doc.get("source_type"):
        out["source_type"] = doc["source_type"]
    out["id"] = doc["id"]
    if doc_path:
        out["path"] = doc_path
    doc_url = doc.get("url")
    if doc_url and doc_url != (f"file://{doc_path}" if doc_path else None):
        out["url"] = doc_url
    out["score_kind"] = doc["score_kind"]
    out["hits"] = hits
    return out


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


def _chunk_parts(chunk_data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Pull ``(text, metadata)`` out of a matched chunk's ``content``.

    v1 puts the raw converted chunk there (``{indexedData, metadata}``); v2
    used to put ``{indexedData}`` only, so v2 hits lost their locator — both
    engines now carry ``metadata`` when the chunk has any.
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


def _strip_context_prefix(text: str, metadata: Dict[str, Any]) -> str:
    """Drop the ``# <path>\\n`` context prefix code chunks embed in their text.

    The indexer prepends the file path so the embedding sees it; the payload
    already carries that path in ``locator.path``, so keeping it would make
    every code hit start with a line the agent has to strip.
    """
    path = metadata.get("file_path")
    if isinstance(path, str) and path:
        prefix = f"# {path}\n"
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def _path_from_url(url: str) -> str:
    """``file:///a/b.py`` -> ``/a/b.py``; anything else is left alone."""
    if url.startswith("file://"):
        return url[len("file://") :]
    return ""


__all__ = ["V1_SCORE_KIND", "build_locator", "build_search_payload"]
