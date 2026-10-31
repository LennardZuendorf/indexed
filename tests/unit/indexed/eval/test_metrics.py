"""Metric arithmetic: the definitions #205 depends on (issue #204).

These are the numbers every later retrieval decision is compared against, so the
edge cases get pinned here rather than discovered in a report: multiple relevant
documents, ties/duplicates, empty results, errors, and unanswerable cases.
"""

from __future__ import annotations

import pytest

from indexed.eval.metrics import (
    aggregate,
    first_relevant_rank,
    rank_documents,
    reciprocal_rank,
    score_case,
)


pytestmark = pytest.mark.unit


def _case(
    ranked,
    relevant,
    *,
    k=5,
    distractors=(),
    error=None,
    case_id="c1",
    query="q",
):
    return score_case(
        case_id=case_id,
        query=query,
        ranked_doc_ids=ranked,
        relevant=relevant,
        k=k,
        distractors=distractors,
        error=error,
    )


def test_hit_and_reciprocal_rank_for_a_single_relevant_document() -> None:
    record = _case(["a.md", "b.md", "target.md"], ["target.md"])
    assert record["status"] == "scored"
    assert record["first_relevant_rank"] == 3
    assert record["reciprocal_rank"] == pytest.approx(1 / 3, abs=1e-6)
    assert record["hit_at_k"] == 1.0


def test_miss_scores_zero_and_reports_no_rank() -> None:
    record = _case(["a.md", "b.md"], ["target.md"])
    assert record["first_relevant_rank"] is None
    assert record["reciprocal_rank"] == 0.0
    assert record["hit_at_k"] == 0.0


def test_multiple_relevant_targets_use_the_best_rank() -> None:
    record = _case(["x.md", "second.md", "y.md", "first.md"], ["first.md", "second.md"])
    assert record["first_relevant_rank"] == 2
    assert record["reciprocal_rank"] == 0.5


def test_a_document_ranked_twice_keeps_its_first_rank() -> None:
    assert rank_documents(["a.md", "a.md", "b.md"]) == ["a.md", "b.md"]
    record = _case(["a.md", "a.md", "target.md", "target.md"], ["target.md"])
    assert record["first_relevant_rank"] == 2


def test_hit_at_k_truncates_but_reciprocal_rank_does_not() -> None:
    record = _case(["a.md", "b.md", "c.md", "target.md"], ["target.md"], k=3)
    assert record["hit_at_k"] == 0.0
    assert record["reciprocal_rank"] == pytest.approx(0.25, abs=1e-6)


def test_empty_result_list_is_a_miss_not_an_error() -> None:
    record = _case([], ["target.md"])
    assert record["status"] == "scored"
    assert record["error"] is None
    assert record["hit_at_k"] == 0.0


def test_an_error_is_a_trusted_context_failure_and_leaves_denominators_alone() -> None:
    broken = _case([], ["target.md"], case_id="broken", error="collection missing")
    assert broken["status"] == "error"
    assert broken["error"] == "collection missing"
    good = _case(["target.md"], ["target.md"], case_id="good")
    metrics = aggregate([broken, good], 5)
    assert metrics["errors"] == 1
    assert metrics["answerable"] == 1
    assert metrics["hit_rate"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["failed_by_id"] == ["broken"]


def test_unanswerable_cases_never_enter_hit_rate_or_mrr() -> None:
    answered = _case(["target.md"], ["target.md"], case_id="answered")
    unanswerable = _case(
        ["tech.md"], [], case_id="unanswerable", distractors=["tech.md"]
    )
    assert unanswerable["status"] == "unanswerable"
    metrics = aggregate([answered, unanswerable], 5)
    assert metrics["answerable"] == 1
    assert metrics["unanswerable"] == 1
    assert metrics["hit_rate"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["unanswerable_distractor_leaks"] == 1


def test_unanswerable_case_without_a_distractor_leak() -> None:
    record = _case(["other.md"], [], distractors=["tech.md"])
    assert record["distractor_leak"] is False


def test_recomputing_metrics_from_saved_records_is_identical() -> None:
    """Keep aggregation reproducible while excluding failures and unanswerable cases."""
    records = [
        _case(["a.md", "target.md"], ["target.md"], case_id="one"),
        _case(["target.md"], ["target.md"], case_id="two"),
        _case(["b.md"], [], case_id="three", distractors=["c.md"]),
        _case([], ["target.md"], case_id="four", error="boom"),
    ]
    first = aggregate(records, 5)
    second = aggregate([dict(record) for record in records], 5)
    assert first == second
    assert first["hit_rate"] == 1.0
    assert first["mrr"] == pytest.approx(0.75, abs=1e-6)


def test_first_relevant_rank_returns_none_for_a_missing_target() -> None:
    assert first_relevant_rank(["a.md"], ["b.md"]) is None
    assert reciprocal_rank(None) == 0.0


def test_k_must_be_positive() -> None:
    with pytest.raises(ValueError):
        _case(["a.md"], ["a.md"], k=0)


def test_aggregate_derives_the_hit_from_the_stored_rank_at_the_requested_k() -> None:
    """`recompute(records, 10)` must be hit@10, not the record's baked hit@5."""
    record = _case(
        [f"doc{n}.md" for n in range(1, 9)] + ["target.md"],
        ["target.md"],
        case_id="ranked-ninth",
    )
    assert record["first_relevant_rank"] == 9
    assert record["hit_at_k"] == 0.0
    assert aggregate([record], 5)["hit_rate"] == 0.0
    wider = aggregate([record], 10)
    assert wider["k"] == 10
    assert wider["hit_rate_at_10"] == 1.0


def test_recompute_derives_leakage_at_requested_cut() -> None:
    record = _case(["safe.md", "near.md"], [], k=1, distractors=["near.md"])
    assert record["distractor_leak"] is False
    assert aggregate([record], 2)["unanswerable_distractor_leaks"] == 1
    assert aggregate([record], 1)["unanswerable_distractor_leaks"] == 0
