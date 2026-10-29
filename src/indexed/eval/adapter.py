"""Adapter: engine result → eval hits (issue #204).

The harness deliberately measures the **retrieval contract**, not a presentation
dialect. The one layer both engines already agree on is the raw result the
``indexed.core.engine`` facade returns::

    {<collection>: {
        "collectionName": str,
        "indexerName": str,          # embedding model id
        "scoreKind": str,            # "cosine" (v2) | "rerank" | absent (v1)
        "results": [{"id": str, "url": str, "path": str,
                     "matchedChunks": [{"chunkNumber": int, "score": float}]}],
    }}

``id`` is the document identity and list order is the rank order — the fields
every downstream envelope (#109, the CLI/MCP projection) preserves, whatever
shape that projection ends up taking. When #108/#109 ratifies a machine
envelope, only this module changes: ``hits_from_engine_result`` is the single
place that knows the dialect.

Kept duck-typed on purpose: it reads dicts and tolerates absent optional keys, so
it can never break because an envelope added a field.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class Hit:
    """One retrieved document (rank level) with its best-scoring chunk."""

    rank: int
    collection: str
    doc_id: str
    doc_name: str
    path: str
    chunk: int
    score: float
    score_kind: str


def _basename(value: str) -> str:
    """Last path segment of an id / path / ``file://`` URI, lower-cased.

    Case documents are named by file (``plan.md``); the engine may key the same
    document by a bare basename (files connector) or by a ``file://`` URI. Both
    normalise to one comparable token here, so a corpus move never invalidates a
    judgement.
    """
    if not value:
        return ""
    text = value
    for prefix in ("file://", "file:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return PurePosixPath(text).name.lower()


def document_identity(entry: Dict[str, Any]) -> Tuple[str, str]:
    """``(doc_id, doc_name)`` for one engine document entry."""
    doc_id = str(entry.get("id") or "")
    path = str(entry.get("path") or entry.get("url") or "")
    doc_name = _basename(doc_id) or _basename(path)
    return doc_id, doc_name


def hits_from_engine_result(
    result: Dict[str, Any], *, collection: str | None = None
) -> Tuple[List[Hit], str | None]:
    """Flatten one facade search result into ranked hits plus an error slot.

    A collection that failed comes back from the facade as ``{"error": ...}``
    (and, for a mixed-engine set, possibly alongside healthy siblings). That is
    reported as the error string — the caller counts it as a trusted-context
    failure, never as a miss.
    """
    if not isinstance(result, dict):
        return [], f"unexpected result type: {type(result).__name__}"

    names = [collection] if collection else [name for name in result]
    hits: List[Hit] = []
    error: str | None = None

    for name in names:
        payload = result.get(name)
        if not isinstance(payload, dict):
            error = error or f"no result payload for collection {name!r}"
            continue
        if payload.get("error"):
            error = error or f"{name}: {payload['error']}"
            continue

        score_kind = str(payload.get("scoreKind") or "")
        results = payload.get("results")
        if not isinstance(results, list):
            # A payload without a result list is not "zero hits": it means the
            # envelope is not the one this adapter understands. Recording it as an
            # error keeps it out of the denominators instead of scoring 0.0 — and
            # stops `--write-baseline` from committing that 0.0 as the baseline.
            error = error or (
                f"{name}: result payload carries no 'results' list "
                f"(got {type(results).__name__})"
            )
            continue
        for rank, entry in enumerate(results, start=1):
            if not isinstance(entry, dict):
                continue
            doc_id, doc_name = document_identity(entry)
            chunks: Sequence[Dict[str, Any]] = entry.get("matchedChunks") or []
            if not chunks:
                hits.append(
                    Hit(
                        rank=rank,
                        collection=name,
                        doc_id=doc_id,
                        doc_name=doc_name,
                        path=str(entry.get("path") or entry.get("url") or ""),
                        chunk=-1,
                        score=0.0,
                        score_kind=score_kind,
                    )
                )
                continue
            for chunk in chunks:
                if not isinstance(chunk, dict):
                    continue
                chunk_number = chunk.get("chunkNumber")
                hits.append(
                    Hit(
                        rank=rank,
                        collection=name,
                        doc_id=doc_id,
                        doc_name=doc_name,
                        path=str(entry.get("path") or entry.get("url") or ""),
                        chunk=-1 if chunk_number is None else int(chunk_number),
                        score=float(chunk.get("score") or 0.0),
                        score_kind=score_kind,
                    )
                )
    return hits, error


def document_ranking(hits: Sequence[Hit]) -> List[str]:
    """Engine document order, de-duplicated, in the adapter's comparable form."""
    return [hit.doc_name for hit in hits if hit.doc_name]


def ranking_detail(
    hits: Sequence[Hit], *, top_k: int | None = None
) -> List[Dict[str, Any]]:
    """Per-document detail for the report: rank, identity, best chunk, score."""
    detail: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        if hit.doc_name in seen:
            continue
        seen.add(hit.doc_name)
        detail.append(
            {
                "rank": len(detail) + 1,
                "doc": hit.doc_name,
                "doc_id": hit.doc_id,
                "chunk": hit.chunk,
                "score": round(hit.score, 6),
                "score_kind": hit.score_kind,
            }
        )
        if top_k is not None and len(detail) >= top_k:
            break
    return detail
