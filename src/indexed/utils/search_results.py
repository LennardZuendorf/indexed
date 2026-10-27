"""The one machine-readable search projection — ``indexed.search.v1``.

Both machine surfaces emit this shape and build it here, so an agent reads ONE
documented contract regardless of transport:

- CLI: ``indexed search --simple-output`` (JSON on stdout);
- MCP: the ``search`` and ``search_collection`` tools (the tool's dict return).

The Rich human view (``cli/knowledge/commands/search_render.py``) uses the same
provenance primitives (``document_path`` / ``document_url`` / ``chunk_locator``)
but renders them; it is not this envelope.

Three rules, each earned by a defect this contract must not reintroduce:

1. **Provenance is honest.** A locator is only the most precise one the chunk's
   own metadata supports, and is ABSENT when unknown — a document-level hit says
   so by omission instead of inventing a line range (Markdown/PDF chunks carry
   ``headings`` only; see #241's findings).
2. **No per-hit boilerplate.** ``rank`` is list position, each collection's
   source type lives once in ``collections``, and totals are one ``count``.
   Nothing has to be stripped before an agent uses the payload.
3. **Nothing is silently dropped.** A hit without text is still a hit, and a
   failed collection always reaches the agent as ``collection_errors`` — an
   index failure can never read as "0 matches".
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional

from indexed.protocols.models import SEARCH_OUTPUT_SCHEMA
from indexed.utils.relevance import HIGHER_IS_BETTER, unified_relevance

# v1 stores the document's *storage* path here (``documents/<id>.json``), which
# is never a locator an agent can act on.
_INTERNAL_PATH_PREFIXES = ("documents/", "indexes/")

# Derived, not recorded: keep the comparable measure short in the payload.
_RELEVANCE_DECIMALS = 6


def document_path(
    document: Mapping[str, Any], metadata: Optional[Mapping[str, Any]] = None
) -> Optional[str]:
    """Best actionable filesystem path for a matched document, or ``None``.

    Order: the chunk's own recorded ``file_path`` (code chunks carry it), then
    the path behind a ``file://`` document URL, then the document's ``path``
    field when it is a real path rather than an internal storage one.
    """
    meta = metadata or {}
    recorded = meta.get("file_path")
    if isinstance(recorded, str) and recorded.strip():
        return recorded

    url = document.get("url")
    if isinstance(url, str) and url.startswith("file://"):
        return url[len("file://") :] or None

    path = document.get("path")
    if isinstance(path, str) and path.strip():
        if "://" in path or path.startswith(_INTERNAL_PATH_PREFIXES):
            return None
        return path
    return None


def document_url(
    document: Mapping[str, Any],
    path: Optional[str],
    source_type: Optional[str] = None,
) -> Optional[str]:
    """Actionable absolute URL for a matched document, or ``None``.

    Never a relative URL: resolving one against a guessed base is exactly the
    fabrication the contract forbids. A ``file://`` URL is dropped when
    ``path`` already names the same location, and a local-file collection
    needs no URL at all once its path is known — both keep the payload small
    without losing where the evidence is.
    """
    url = document.get("url")
    if not isinstance(url, str) or "://" not in url:
        return None
    if path and (source_type == "localFiles" or url.startswith("file://")):
        return None
    return url


def chunk_locator(metadata: Optional[Mapping[str, Any]]) -> Optional[dict]:
    """Most precise locator the chunk metadata supports, or ``None``.

    ``lines`` is emitted 1-based and inclusive; indexed records 0-based
    inclusive spans (tree-sitter / line fallback), so the conversion happens
    here, once. Headings come next (prose), then a page number (paged sources).
    """
    meta = metadata or {}

    start, end = meta.get("start_line"), meta.get("end_line")
    if (
        isinstance(start, int)
        and isinstance(end, int)
        and not isinstance(start, bool)
        and not isinstance(end, bool)
        and 0 <= start <= end
    ):
        # 0-based inclusive -> 1-based inclusive.
        return {"lines": [start + 1, end + 1]}

    headings = meta.get("headings")
    if isinstance(headings, (list, tuple)) and headings:
        return {"headings": [str(h) for h in headings]}

    page = meta.get("page")
    if isinstance(page, int) and not isinstance(page, bool) and page > 0:
        return {"page": page}
    return None


def chunk_metadata(chunk: Mapping[str, Any]) -> dict:
    """Per-chunk source metadata, from either engine's raw chunk shape.

    v1 nests the on-disk chunk dict under ``content`` (``indexedData`` +
    optional ``metadata``); v2's projection mirrors that, but a chunk carrying
    metadata beside ``content`` is accepted too rather than dropped.
    """
    content = chunk.get("content")
    if isinstance(content, dict):
        meta = content.get("metadata")
        if isinstance(meta, dict):
            return meta
    meta = chunk.get("metadata")
    return meta if isinstance(meta, dict) else {}


def chunk_text(chunk: Mapping[str, Any]) -> Optional[str]:
    """The matched chunk's text, or ``None`` when the engine sent none."""
    content = chunk.get("content")
    if isinstance(content, dict):
        raw = content.get("indexedData")
        return raw if isinstance(raw, str) else None
    return content if isinstance(content, str) else None


def build_search_envelope(
    raw_results: Mapping[str, Any],
    query: str,
    *,
    source_types: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Project per-collection raw search results into ``indexed.search.v1``.

    ``raw_results`` is the engine facade's return: collection name ->
    ``{collectionName, indexerName, scoreKind?, results: [...]}`` or
    ``{"error": ...}``. ``source_types`` maps collection name -> source type for
    the collections this search actually resolved; unknown names are simply
    absent from the envelope's ``collections`` map (never guessed).

    Ranking is unchanged from the pre-contract formatter: a view containing any
    higher-is-better engine (v2 cosine/rerank) ranks every hit on the one
    comparable ``relevance`` measure, best first; a v1-only view keeps raw
    ascending squared-L2 distance and carries no ``relevance``/``score_kind``.
    """
    known_types = source_types or {}
    collections: Dict[str, str] = {}
    collection_errors: List[Dict[str, str]] = []
    candidates: List[Dict[str, Any]] = []
    any_higher_is_better = False

    for collection_name, collection_data in raw_results.items():
        source_type = known_types.get(collection_name)
        if isinstance(source_type, str) and source_type:
            collections[collection_name] = source_type

        if not isinstance(collection_data, dict):
            collection_errors.append(
                {"collection": collection_name, "error": "malformed result"}
            )
            continue
        if "error" in collection_data:
            collection_errors.append(
                {"collection": collection_name, "error": str(collection_data["error"])}
            )
            continue

        raw_score_kind = collection_data.get("scoreKind")
        score_kind = raw_score_kind if raw_score_kind in HIGHER_IS_BETTER else None
        any_higher_is_better = any_higher_is_better or score_kind is not None

        for document in collection_data.get("results") or []:
            if not isinstance(document, dict):
                continue
            for chunk in _chunks_of(document):
                metadata = chunk_metadata(chunk)
                path = document_path(document, metadata)
                candidates.append(
                    {
                        "collection": collection_name,
                        "path": path,
                        "url": document_url(document, path, source_type),
                        "locator": chunk_locator(metadata),
                        "chunk": _int_or(chunk.get("chunkNumber"), 0),
                        "score": _float_or(chunk.get("score"), 0.0),
                        "score_kind": score_kind,
                        "text": chunk_text(chunk),
                    }
                )

    _rank(candidates, unified=any_higher_is_better)

    results = [_hit(candidate) for candidate in candidates]
    return {
        "schema": SEARCH_OUTPUT_SCHEMA,
        "query": query,
        "count": len(results),
        "collections": collections,
        "collection_errors": collection_errors,
        "results": results,
    }


def _chunks_of(document: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    chunks = document.get("matchedChunks")
    if chunks is None:
        chunks = document.get("matched_chunks")
    for chunk in chunks or []:
        if isinstance(chunk, dict):
            yield chunk


def _rank(candidates: List[Dict[str, Any]], *, unified: bool) -> None:
    """Order ``candidates`` best-first in place (stable within a score tie)."""
    if not unified:
        candidates.sort(key=lambda c: c["score"])
        return
    for candidate in candidates:
        candidate["relevance"] = round(
            unified_relevance(candidate["score"], candidate["score_kind"] or ""),
            _RELEVANCE_DECIMALS,
        )
    candidates.sort(key=lambda c: c["relevance"], reverse=True)


def _hit(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """One hit dict, unset fields omitted (never emitted as null)."""
    hit: Dict[str, Any] = {"collection": candidate["collection"]}
    if candidate["path"]:
        hit["path"] = candidate["path"]
    if candidate["url"]:
        hit["url"] = candidate["url"]
    if candidate["locator"]:
        hit["locator"] = candidate["locator"]
    hit["chunk"] = candidate["chunk"]
    hit["score"] = candidate["score"]
    if candidate["score_kind"]:
        hit["score_kind"] = candidate["score_kind"]
    if candidate["relevance"] is not None:
        hit["relevance"] = candidate["relevance"]
    if candidate["text"]:
        hit["text"] = candidate["text"]
    return hit


def _int_or(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "build_search_envelope",
    "chunk_locator",
    "chunk_metadata",
    "chunk_text",
    "document_path",
    "document_url",
]
