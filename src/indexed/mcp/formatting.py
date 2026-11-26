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
and text — plus `sources`, one record per source the request *intended* to
search saying whether it answered.

`sources` is the honesty half (issue #340). `collections` and
`collection_errors` are derived from what the engine returned, so a source that
was never built, whose index was deleted, or that indexes nothing used to leave
no trace at all: "two sources answered" and "three were meant to, one died"
looked identical. The builder never invents a source: callers pass the intended
scope they resolved (see `indexed.cli.search_sources`), and an undeclared
collection the engine did answer is appended as `ok` — or as `failed` when the
engine returned an error for it — rather than hidden.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, cast

from indexed.protocols.results import SEARCH_SCHEMA, Hit, SourceState, SourceStatus
from indexed.utils.git_meta import (
    filter_skip_message,
    line_blame_skip_message,
    provenance_skip_message,
    rerank_skip_message,
)
from indexed.utils.provenance import build_locator, chunk_parts, strip_context_prefix
from indexed.utils.relevance import V1_SCORE_KIND, unified_relevance

#: Precision of emitted floats; ranking retains full precision internally.
_SCORE_DECIMALS = 4

#: ``sources`` is a per-source verdict, not a second document list: a record
#: that is not ``ok`` always carries an ``error``, because a silent status is the
#: failure this field exists to prevent.
_NON_OK_STATUSES = frozenset({"empty", "missing", "unusable", "failed"})

#: Fallback wording when a caller passes a verdict without an explanation. A
#: status with no sentence beside it is the silence this field exists to remove.
_STATUS_DEFAULT_ERROR = {
    "empty": "indexes no documents, so nothing can match; re-run indexing for it.",
    "missing": "is not in the store; re-create or re-index it.",
    "unusable": "has no usable index; re-index it.",
    "failed": "could not be searched.",
}


def build_search_payload(
    raw_results: Dict[str, Any],
    query: str,
    *,
    sources: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Turn the core search result into the documented payload.

    ``raw_results`` maps collection name -> per-collection result, as returned
    by ``indexed.core.engine.search`` (v1 or v2). Each collection may carry
    ``error``, ``results`` and — from this schema on — ``sourceType`` and
    ``scoreKind``. Collections arrive already fetched with matched-chunk
    content (``include_matched_chunks=True``), because the locator and the
    text both live in a chunk's ``content``/``metadata``.

    ``sources`` is the *intended* scope, in order, as resolved by the caller
    (``indexed.cli.search_sources.declare_sources``): ``{"collection": str,
    "status"?, "source_type"?, "documents"?, "error"?}``. Absent means "no
    intent beyond what the engine answered", which is what a test double and an
    ad-hoc caller have; the answered collections then become the source list.
    """
    collection_errors: List[Dict[str, Any]] = []
    searched: List[str] = []
    freshness: List[Dict[str, Any]] = []
    # Declarations decide a source's verdict when the engine cannot (missing,
    # unusable, empty), so their error replaces the engine's lookalike one.
    declared: Dict[str, Mapping[str, Any]] = {
        str(entry["collection"]): entry for entry in sources or ()
    }
    # (collection, document key) -> document payload under construction.
    documents: Dict[Tuple[str, str], Dict[str, Any]] = {}
    # Flat ranking list; grouping happens after the sort, so a document's
    # position reflects its BEST hit (v1 `__build_results` semantics).
    ranked: List[Tuple[float, Tuple[str, str], Hit]] = []
    hits_per_collection: Dict[str, int] = {}

    for collection_name, collection_data in raw_results.items():
        declaration = declared.get(collection_name)
        if declaration is not None and declaration.get("status") in _NON_OK_STATUSES:
            # The caller already knows why this one did not answer; its verdict
            # and wording win over whatever the engine put in the dict.
            continue

        if isinstance(collection_data, dict) and "error" in collection_data:
            # The failure becomes a `failed` record in `sources` below, which
            # mirrors it into `collection_errors` exactly once — appending it
            # here too repeated every declared engine failure (#340 review).
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
        # And for the two annotations (dogfood M7): a v1 collection returns no
        # git block at all, so a requested provenance/blame that produced none
        # must say why rather than read as "this file has no commit".
        for status_key, message in (
            ("gitProvenance", provenance_skip_message),
            ("gitLineBlame", line_blame_skip_message),
        ):
            status = collection_data.get(status_key)
            if isinstance(status, dict) and status.get("applied") is False:
                collection_errors.append(
                    {
                        "collection": collection_name,
                        "error": message(status),
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
                # A comment has its own address under the issue: state it on the
                # hit, because "the issue" would send a reader to the wrong place
                # (#340 R1). Only when it says more than the document already does.
                comment_url = metadata.get("commentUrl")
                if (
                    isinstance(comment_url, str)
                    and comment_url
                    and comment_url != doc_url
                ):
                    hit["url"] = comment_url
                line_git = chunk_data.get("git")
                if isinstance(line_git, dict):
                    hit["git"] = line_git
                ranked.append((relevance, key, hit))
                hits_per_collection[collection_name] = (
                    hits_per_collection.get(collection_name, 0) + 1
                )

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

    source_states = _build_sources(
        sources=sources,
        raw_results=raw_results,
        collections=searched,
        hits_per_collection=hits_per_collection,
    )
    # A source record that is not `ok` is an error the flat list must also name,
    # so a consumer (or renderer) predating `sources` is never told less.
    for state in source_states:
        if state["status"] == "ok":
            continue
        collection_errors.append(
            {"collection": state["collection"], "error": state.get("error", "")}
        )

    # `collections` lists what was SEARCHED. A source that answered `empty` or
    # `failed` matched nothing because it answered nothing, so listing it here
    # would let a consumer read a dead source as a legitimate no-match. This is
    # the documented contract (docs/reference/search-output.md): every non-`ok`
    # source is absent from `collections` and named in `sources` instead.
    non_ok = {state["collection"] for state in source_states if state["status"] != "ok"}
    answered_collections = [name for name in searched if name not in non_ok]
    answered_freshness = [
        entry for entry in freshness if entry["collection"] not in non_ok
    ]

    payload = {
        "schema": SEARCH_SCHEMA,
        "query": query,
        "counts": {"documents": len(documents_out), "hits": len(ranked)},
        "collections": answered_collections,
        "collection_errors": collection_errors,
        "sources": source_states,
        "documents": documents_out,
    }
    if answered_freshness:
        payload["freshness"] = answered_freshness
    return payload


def _build_sources(
    *,
    sources: Optional[Sequence[Mapping[str, Any]]],
    raw_results: Dict[str, Any],
    collections: List[str],
    hits_per_collection: Dict[str, int],
) -> List[SourceState]:
    """One ``sources`` record per intended source, then any undeclared answerer.

    The caller's declaration decides the verdict where it has one; otherwise the
    engine's own answer does: an ``error`` entry is ``failed``, an answered
    collection is ``ok``. A declared name the engine never mentioned was not
    searched — it keeps the caller's ``missing``/``unusable`` and its error,
    which is precisely the case that used to disappear. A failure the caller
    never declared (no selection, ``--collection``) is still a source that was
    handed to the engine, so it is appended as ``failed`` rather than left to
    ``collection_errors`` alone.
    """
    states: List[SourceState] = []
    seen: set[str] = set()
    for declaration in sources or ():
        name = str(declaration["collection"])
        if name in seen:
            continue
        seen.add(name)
        data = raw_results.get(name)
        declared_status = declaration.get("status")
        documents = declaration.get("documents")
        if declared_status in _NON_OK_STATUSES:
            status: SourceStatus = cast(SourceStatus, declared_status)
        elif isinstance(data, dict) and "error" in data:
            status = "failed"
        else:
            status = "ok"
        # R3: a source that indexes nothing is NEVER `ok`. Two statements can
        # say so, and either is enough: the manifest counts zero documents, or
        # the index the engine just opened holds zero vectors (a partially
        # rebuilt collection still claims documents it can no longer match).
        index_size = data.get("indexSize") if isinstance(data, dict) else None
        if status == "ok" and index_size == 0:
            status = "empty"
            documents = 0
        elif status == "ok" and documents == 0:
            status = "empty"

        state: SourceState = {"collection": name, "status": status}
        source_type = declaration.get("source_type") or (
            data.get("sourceType") if isinstance(data, dict) else None
        )
        if source_type:
            state["source_type"] = str(source_type)
        if isinstance(documents, int):
            state["documents"] = documents
        if name in collections:
            state["hits"] = hits_per_collection.get(name, 0)
        if status != "ok":
            engine_error = data.get("error") if isinstance(data, dict) else None
            state["error"] = str(
                declaration.get("error")
                or engine_error
                or f"Collection '{name}' {_STATUS_DEFAULT_ERROR[status]}"
            )
        states.append(state)

    for name, data in raw_results.items():
        if name in seen:
            continue
        seen.add(name)
        if not isinstance(data, dict):
            continue
        if "error" in data:
            # An undeclared failure is still a source the request meant to use:
            # MCP `search` without a selection and CLI `--collection` have no
            # declarations, and a failure there used to vanish from `sources`
            # while lingering in `collection_errors` (#340 review).
            states.append(
                {
                    "collection": name,
                    "status": "failed",
                    "error": str(data["error"]),
                }
            )
            continue
        if name not in collections:
            continue
        hits = hits_per_collection.get(name, 0)
        source_type = data.get("sourceType")
        answered: SourceState
        if source_type:
            answered = {
                "collection": name,
                "source_type": str(source_type),
                "status": "ok",
                "hits": hits,
            }
        else:
            answered = {"collection": name, "status": "ok", "hits": hits}
        states.append(answered)

    return states


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
