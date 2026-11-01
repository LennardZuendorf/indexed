"""Retrieval-eval arithmetic: pure, deterministic, model-free (issue #204).

The definitions below are the contract — a metric change is a schema change, so
it gets stated here once instead of being re-invented per report:

* Ranking is **document-level**. The engine returns documents in rank order and
  a document's rank is its first position in that list (1-based). A document
  returned twice keeps its first rank; later apparences never improve it.
* ``hit@k`` is 1.0 when at least one relevant document is ranked at or above
  ``k``, else 0.0. Hit-rate is its mean over **answerable** cases.
* ``reciprocal rank`` is ``1 / rank`` of the first relevant document, using the
  whole returned ranking rather than truncating at ``k``; 0.0 when no relevant
  document was returned at all. MRR is its mean over **answerable** cases.
* Ties keep the engine's own order — no tie-break is invented here, so metric
  computation repeated on a saved ranking is byte-identical.
* A case that errored (collection error, missing collection, unreachable
  source) is a **trusted-context failure**, not a miss: it is excluded from both
  denominators and counted in ``errors``. An empty result list is not an error —
  it scores 0.0. When nothing is answerable, ``hit_rate``/``mrr`` are ``None``:
  no measurement, rather than a fabricated 0.0.
* A case with an empty ``relevant`` list is **unanswerable** and is never folded
  into hit-rate or MRR. It is scored on the separate slice ``answerable: false``
  and only reports ``distractor_leak``: whether a near-miss document from the
  case's ``distractors`` reached the top ``k``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

#: Number of decimals kept in every emitted metric, so reports diff cleanly.
PRECISION = 6

STATUS_SCORED = "scored"
STATUS_UNANSWERABLE = "unanswerable"
STATUS_ERROR = "error"


def _r(value: float) -> float:
    return round(float(value), PRECISION)


def rank_documents(doc_ids: Sequence[str]) -> List[str]:
    """Document ranking from an engine-ordered hit list, first occurrence wins."""
    seen: Dict[str, None] = {}
    for doc_id in doc_ids:
        seen.setdefault(doc_id, None)
    return list(seen)


def first_relevant_rank(
    ranked: Sequence[str], relevant: Sequence[str]
) -> Optional[int]:
    """1-based rank of the first relevant document, or ``None`` if absent."""
    wanted = set(relevant)
    for position, doc_id in enumerate(rank_documents(ranked), start=1):
        if doc_id in wanted:
            return position
    return None


def reciprocal_rank(rank: Optional[int]) -> float:
    """``1/rank``, or 0.0 when nothing relevant was ranked."""
    return 0.0 if rank is None else _r(1.0 / rank)


def score_case(
    *,
    case_id: str,
    query: str,
    ranked_doc_ids: Sequence[str],
    relevant: Sequence[str],
    k: int,
    distractors: Sequence[str] = (),
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Score one case against the documents the engine actually returned.

    ``ranked_doc_ids`` is the engine's document order (one entry per returned
    document, duplicates allowed). The per-case record is the report's unit of
    evidence: it carries the ranking, the judgement and the arithmetic that
    produced them, so ``aggregate`` can be re-run on a saved report.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")

    ranked = rank_documents(ranked_doc_ids)
    record: Dict[str, Any] = {
        "id": case_id,
        "query": query,
        "relevant": list(relevant),
        "distractors": list(distractors),
        "ranked_docs": ranked,
        "k": k,
        "first_relevant_rank": None,
        "reciprocal_rank": 0.0,
        "hit_at_k": 0.0,
        # Only an unanswerable case is scored on leaks; leaving this None on a
        # scored case keeps "not measured" distinct from "measured, no leak".
        "distractor_leak": None,
        "error": error,
    }

    if error is not None:
        record["status"] = STATUS_ERROR
        return record

    if not relevant:
        ranked_set = set(ranked[:k])
        record["status"] = STATUS_UNANSWERABLE
        record["distractor_leak"] = bool(ranked_set & set(distractors))
        return record

    rank = first_relevant_rank(ranked, relevant)
    record["status"] = STATUS_SCORED
    record["first_relevant_rank"] = rank
    record["reciprocal_rank"] = reciprocal_rank(rank)
    record["hit_at_k"] = 1.0 if rank is not None and rank <= k else 0.0
    return record


def aggregate(per_query: Sequence[Dict[str, Any]], k: int) -> Dict[str, Any]:
    """Aggregate per-case records into the report's headline numbers.

    Reads only the per-case records, so recomputing the metrics of a saved
    report reproduces the original numbers exactly.
    """
    scored = [case for case in per_query if case.get("status") == STATUS_SCORED]
    unanswerable = [
        case for case in per_query if case.get("status") == STATUS_UNANSWERABLE
    ]
    errors = [case for case in per_query if case.get("status") == STATUS_ERROR]
    unknown = [
        case.get("id")
        for case in per_query
        if case.get("status") not in {STATUS_SCORED, STATUS_UNANSWERABLE, STATUS_ERROR}
    ]
    if unknown:
        raise ValueError(f"case records with an unknown status: {unknown}")

    # No scored case means there is no measurement: emit None rather than 0.0 so
    # an all-errored run cannot read as "we measured a total retrieval failure".
    # The hit is derived from the stored rank, not from the record's own
    # `hit_at_k`: the latter was baked at the record's k, so trusting it would let
    # `recompute(report["queries"], 10)` label a hit@5 number as hit@10.
    hit_rate = (
        sum(
            1.0
            for case in scored
            if case.get("first_relevant_rank") is not None
            and case["first_relevant_rank"] <= k
        )
        / len(scored)
        if scored
        else None
    )
    mrr = (
        sum(case["reciprocal_rank"] for case in scored) / len(scored)
        if scored
        else None
    )
    leaks = sum(
        bool(set(rank_documents(case["ranked_docs"])[:k]) & set(case["distractors"]))
        for case in unanswerable
    )

    return {
        "k": k,
        "cases": len(per_query),
        "answerable": len(scored),
        "unanswerable": len(unanswerable),
        "errors": len(errors),
        "hit_rate": None if hit_rate is None else _r(hit_rate),
        f"hit_rate_at_{k}": None if hit_rate is None else _r(hit_rate),
        "mrr": None if mrr is None else _r(mrr),
        "unanswerable_distractor_leaks": leaks,
        "failed_by_id": [case["id"] for case in errors],
    }


def recompute(per_query: Sequence[Dict[str, Any]], k: int) -> Dict[str, Any]:
    """Alias kept explicit: metric recomputation must not need the engine."""
    return aggregate(per_query, k)
