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
import math
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

    names = [collection] if collection else list(result)
    hits: List[Hit] = []
    for name in names:
        payload = result.get(name)
        if not isinstance(payload, dict):
            return [], f"no result payload for collection {name!r}"
        failure = payload.get("error")
        if failure is not None and not isinstance(failure, str):
            return [], f"{name}: error must be a string or null"
        if failure:
            return [], f"{name}: {failure}"
        for key in ("collectionName", "indexerName", "scoreKind"):
            if key in payload and not isinstance(payload[key], str):
                return [], f"{name}: {key} must be a string"
        score_kind = payload.get("scoreKind", "")
        results = payload.get("results")
        if not isinstance(results, list):
            return (
                [],
                f"{name}: result payload carries no 'results' list (got {type(results).__name__})",
            )
        for rank, entry in enumerate(results, start=1):
            where = f"{name}: results[{rank - 1}]"
            try:
                if not isinstance(entry, dict):
                    raise ValueError("document must be an object")
                for key in ("id", "path", "url"):
                    if key in entry and not isinstance(entry[key], str):
                        raise ValueError(f"{key} must be a string")
                    if key in entry and entry[key] != entry[key].strip():
                        raise ValueError(f"{key} has ambiguous whitespace")
                doc_id, doc_name = document_identity(entry)
                if not doc_name or doc_name in {".", ".."}:
                    raise ValueError("document identity is missing")
                chunks = entry.get("matchedChunks", [])
                if not isinstance(chunks, list):
                    raise ValueError("matchedChunks must be a list")
                for chunk in chunks or [{}]:
                    if not isinstance(chunk, dict):
                        raise ValueError("matchedChunks entry must be an object")
                    number = chunk.get("chunkNumber")
                    if number is not None and (type(number) is not int or number < -1):
                        raise ValueError("chunkNumber must be an integer or null")
                    score = chunk.get("score", 0.0)
                    if (
                        isinstance(score, bool)
                        or not isinstance(score, (int, float))
                        or not math.isfinite(score)
                    ):
                        raise ValueError("score must be a finite number")
                    hits.append(
                        Hit(
                            rank=rank,
                            collection=name,
                            doc_id=doc_id,
                            doc_name=doc_name,
                            path=entry.get("path") or entry.get("url") or "",
                            chunk=-1 if number is None else number,
                            score=float(score),
                            score_kind=score_kind,
                        )
                    )
            except (ValueError, OverflowError) as exc:
                return [], f"{where}: {exc}"
    return hits, None


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
