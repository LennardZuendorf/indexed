"""Baseline-vs-candidate comparison verdicts (issue #204)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from indexed.eval.compare import (
    VERDICT_IMPROVED,
    VERDICT_INCOMPARABLE,
    VERDICT_REGRESSED,
    VERDICT_UNCHANGED,
    compare_reports,
    exit_code,
    format_summary,
)


def _query(
    case_id: str, rank: Optional[int], *, error: Optional[str] = None
) -> Dict[str, Any]:
    rr = 0.0 if not rank else round(1.0 / rank, 6)
    return {
        "id": case_id,
        "first_relevant_rank": rank,
        "reciprocal_rank": rr,
        "hit_at_k": 1.0 if rank and rank <= 5 else 0.0,
        "error": error,
        "status": "error" if error else "scored",
    }


def _report(
    queries,
    *,
    hit_rate: float,
    mrr: float,
    corpus: str = "tree-a",
    cases: str = "cases-a",
    config: Optional[Dict[str, Any]] = None,
    leaks: Optional[int] = None,
) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {"k": 5, "hit_rate": hit_rate, "mrr": mrr}
    if leaks is not None:
        metrics["unanswerable_distractor_leaks"] = leaks
    return {
        "schema": "indexed.eval.report.v1",
        "generated_at": "2026-10-26T00:00:00+00:00",
        "corpus": {"tree_sha256": corpus},
        "case_set": {"sha256": cases},
        "config": config or {"embedding_model": "m1", "score_kind": "cosine"},
        "metrics": metrics,
        "queries": queries,
    }


def test_identical_reports_are_unchanged_and_exit_zero() -> None:
    queries = [_query("a", 1), _query("b", 3)]
    baseline = _report(queries, hit_rate=1.0, mrr=0.666667)
    result = compare_reports(baseline, baseline)
    assert result["verdict"] == VERDICT_UNCHANGED
    assert result["comparable"] is True
    assert exit_code(result) == 0
    assert result["improved"] == []
    assert result["regressed"] == []


def test_a_better_rank_is_an_improvement() -> None:
    baseline = _report([_query("a", 4)], hit_rate=1.0, mrr=0.25)
    candidate = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    result = compare_reports(baseline, candidate)
    assert result["verdict"] == VERDICT_IMPROVED
    assert exit_code(result) == 0
    assert result["improved"] == [{"id": "a", "rank_before": 4, "rank_after": 1}]


def test_a_worse_rank_is_a_regression_and_exits_one() -> None:
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    candidate = _report([_query("a", 5)], hit_rate=1.0, mrr=0.2)
    result = compare_reports(baseline, candidate)
    assert result["verdict"] == VERDICT_REGRESSED
    assert exit_code(result) == 1
    assert result["regressed"] == [{"id": "a", "rank_before": 1, "rank_after": 5}]


def test_a_new_failure_is_a_regression_even_when_metrics_tie() -> None:
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    candidate = _report(
        [_query("a", 1), _query("b", None, error="collection missing")],
        hit_rate=1.0,
        mrr=1.0,
    )
    result = compare_reports(baseline, candidate)
    assert result["verdict"] == VERDICT_REGRESSED
    assert result["newly_failed"] == ["b"]


def test_a_different_corpus_is_not_comparable_and_exits_two() -> None:
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0, corpus="tree-a")
    candidate = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0, corpus="tree-b")
    result = compare_reports(baseline, candidate)
    assert result["verdict"] == VERDICT_INCOMPARABLE
    assert result["comparable"] is False
    assert any(
        "corpus tree differs" in reason for reason in result["incomparable_reasons"]
    )
    assert exit_code(result) == 2


def test_a_different_case_set_is_not_comparable() -> None:
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0, cases="cases-a")
    candidate = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0, cases="cases-b")
    result = compare_reports(baseline, candidate)
    assert result["verdict"] == VERDICT_INCOMPARABLE
    assert any(
        "case set differs" in reason for reason in result["incomparable_reasons"]
    )


def test_a_configuration_change_makes_the_comparison_incomparable() -> None:
    """A model/knob swap moves the numbers without being a ranking win."""
    baseline = _report(
        [_query("a", 2)],
        hit_rate=1.0,
        mrr=0.5,
        config={"embedding_model": "m1", "score_kind": "cosine", "rerank": False},
    )
    candidate = _report(
        [_query("a", 1)],
        hit_rate=1.0,
        mrr=1.0,
        config={"embedding_model": "m1", "score_kind": "rerank", "rerank": True},
    )
    result = compare_reports(baseline, candidate)
    assert result["verdict"] == VERDICT_INCOMPARABLE
    assert exit_code(result) == 2
    assert result["config_changes"]["rerank"] == {"baseline": False, "candidate": True}
    assert result["config_changes"]["score_kind"]["candidate"] == "rerank"
    summary = format_summary(result)
    assert "verdict: incomparable" in summary
    assert "config rerank: False -> True" in summary
    # The metric delta is still reported — the comparison is refused, not hidden.
    assert "hit_rate 1.000 -> 1.000" in summary


def test_tolerance_absorbs_noise() -> None:
    baseline = _report([_query("a", 2)], hit_rate=1.0, mrr=0.5)
    candidate = _report([_query("a", 3)], hit_rate=1.0, mrr=0.333333)
    assert compare_reports(baseline, candidate)["verdict"] == VERDICT_REGRESSED
    assert (
        compare_reports(baseline, candidate, tolerance=0.2)["verdict"]
        == VERDICT_UNCHANGED
    )


def test_a_compensating_pair_is_still_a_regression() -> None:
    """One case up and one down nets to zero: the loss must still fail the gate."""
    baseline = _report([_query("a", 1), _query("b", 2)], hit_rate=1.0, mrr=0.75)
    candidate = _report([_query("a", 2), _query("b", 1)], hit_rate=1.0, mrr=0.75)
    result = compare_reports(baseline, candidate)
    assert result["metrics"]["delta"]["mrr"] == 0.0
    assert result["verdict"] == VERDICT_REGRESSED
    assert exit_code(result) == 1
    assert result["regressed"] == [{"id": "a", "rank_before": 1, "rank_after": 2}]


def test_a_leak_increase_is_a_regression() -> None:
    """Unanswerable cases have to be able to move the verdict, not just decorate it."""
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0, leaks=2)
    candidate = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0, leaks=3)
    result = compare_reports(baseline, candidate)
    assert result["verdict"] == VERDICT_REGRESSED
    assert result["metrics"]["delta"]["unanswerable_distractor_leaks"] == 1.0
    assert "distractor_leak 2 -> 3" in format_summary(result)


def test_a_leak_decrease_is_an_improvement() -> None:
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0, leaks=3)
    candidate = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0, leaks=2)
    assert compare_reports(baseline, candidate)["verdict"] == VERDICT_IMPROVED
