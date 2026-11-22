"""The machine-readable search payload (``indexed.search/1``).

This is the success result shape for machine consumers: the MCP ``search`` /
``search_collection`` tools return it, and the CLI emits it under
``indexed index search --json`` (``--simple-output`` is the legacy alias).
CLI consumers check exit status before JSON parsing; escaping errors can write
non-JSON stdout. Normal JSON and MCP responses discriminate on ``schema``.
The contract is typed in ``indexed.protocols.results`` and documented for users
in ``docs/reference/search-output.md``; ``docs/spec/tech/app/app-search-result-contract.md``
stays the design record (issues #108/#109).

Shape, in one breath: documents grouped, each stating its collection, source
type, id, url, git provenance (when it was asked for and git answered) and
score semantics ONCE; each hit carrying only its relevance, raw score, locator
and text.

Grouping was the point. The old flat payload repeated ``collection``,
``document_id`` and ``document_url`` on every chunk and said nothing about
WHERE the chunk sits — the two costs that made MCP output both bulky and
unactionable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from indexed.protocols.results import SEARCH_SCHEMA, Hit
from indexed.utils.git_meta import filter_skip_message, rerank_skip_message
from indexed.utils.provenance import build_locator, chunk_parts, strip_context_prefix
from indexed.utils.relevance import V1_SCORE_KIND, unified_relevance

#: Precision of emitted floats; ranking retains full precision internally.
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
    freshness: List[Dict[str, Any]] = []
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

        # A requested changed_since the collection could not honour is reported
        # here too: unfiltered rows arriving under a "changed only" request are
        # a defect, not a quiet degrade (#279 review, finding 1).
        git_filter = collection_data.get("gitFilter")
        if isinstance(git_filter, dict) and git_filter.get("applied") is False:
            collection_errors.append(
                {
                    "collection": collection_name,
                    "error": filter_skip_message(git_filter),
                }
            )
        # Same rule for a requested git re-rank (#144): rows that were not
        # re-ranked must not look re-ranked.
        git_rerank = collection_data.get("gitRerank")
        if isinstance(git_rerank, dict) and git_rerank.get("applied") is False:
            collection_errors.append(
                {
                    "collection": collection_name,
                    "error": rerank_skip_message(git_rerank),
                }
            )

        verdict = collection_data.get("freshness")
        if isinstance(verdict, dict):
            freshness.append({"collection": collection_name, **verdict})

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
                # Key order is the documented one (docs/spec/tech/app/app-search-result-contract.md):
                # document facts first, hits last.
                entry: Dict[str, Any] = {"collection": collection_name}
                if source_type:
                    entry["source_type"] = source_type
                entry["id"] = doc_id
                if doc_url:
                    entry["url"] = doc_url
                # Document-level provenance, present only when --git-provenance
                # found a commit for this file (v2 files collections); absent
                # otherwise. Facts about the file, so they sit on the document
                # rather than repeated on every hit (#279 x #297 result shape).
                git = doc.get("git")
                if isinstance(git, dict):
                    entry["git"] = git
                entry["score_kind"] = score_kind
                entry["hits"] = []
                documents[key] = entry  # type: ignore[assignment]

            for chunk_data in doc.get("matchedChunks", []) or []:
                text, metadata = chunk_parts(chunk_data)
                if not text:
                    continue
                raw_score = float(chunk_data.get("score", 0.0) or 0.0)
                locator = build_locator(metadata, doc_url)
                relevance = unified_relevance(raw_score, score_kind)
                hit: Hit = {
                    "relevance": round(relevance, _SCORE_DECIMALS),
                    "score": round(raw_score, _SCORE_DECIMALS),
                    "locator": locator,
                    "text": strip_context_prefix(text, metadata),
                }
                line_git = chunk_data.get("git")
                if isinstance(line_git, dict):
                    hit["git"] = line_git
                ranked.append((relevance, key, hit))

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

    payload = {
        "schema": SEARCH_SCHEMA,
        "query": query,
        "counts": {"documents": len(documents_out), "hits": len(ranked)},
        "collections": searched,
        "collection_errors": collection_errors,
        "documents": documents_out,
    }
    if freshness:
        payload["freshness"] = freshness
    return payload


def _finalize_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Hoist the repeated per-hit path/url onto the document, then reorder keys.

    A document's hits nearly always sit in the same file, so repeating an
    absolute path on every hit is exactly the boilerplate this shape exists to
    remove (it measured LARGER than the payload it replaced). The path is
    stated once on the document and stripped from the hits when exactly one
    distinct locator path exists. Multiple paths omit document ``path`` and
    stay on their respective locators. Likewise a ``file://`` url that only
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
    # Provenance is a fact about the file, stated once beside the url; absent
    # unless --git-provenance got an answer for the indexed snapshot.
    if doc.get("git"):
        out["git"] = doc["git"]
    out["score_kind"] = doc["score_kind"]
    out["hits"] = hits
    return out


__all__ = ["V1_SCORE_KIND", "build_locator", "build_search_payload"]
