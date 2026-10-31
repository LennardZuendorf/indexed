"""Baseline-vs-candidate comparison verdicts (issue #204)."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from indexed.eval.compare import (
    VERDICT_IMPROVED,
    VERDICT_INCOMPARABLE,
    VERDICT_REGRESSED,
    VERDICT_UNCHANGED,
    compare_reports,
    exit_code,
    format_summary,
)


pytestmark = pytest.mark.unit


def _query(
    case_id: str, rank: Optional[int], *, error: Optional[str] = None
) -> Dict[str, Any]:
    """Create ordered target evidence with matching per-query metrics and status."""
    rr = 0.0 if not rank else round(1.0 / rank, 6)
    ranked = [f"other-{n}.md" for n in range(1, rank or 1)] + (
        ["target.md"] if rank else []
    )
    return {
        "id": case_id,
        "query": "query",
        "provenance": "issue title",
        "rationale": "target answers the question",
        "relevant": ["target.md"],
        "distractors": [],
        "ranked_docs": ranked,
        "ranking": [
            {"rank": n, "doc": doc, "chunk": 0, "score": 0.9, "score_kind": "cosine"}
            for n, doc in enumerate(ranked, 1)
        ],
        "k": 5,
        "elapsed_ms": 1.0,
        "distractor_leak": None,
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
) -> Dict[str, Any]:
    """Assemble report counts and failures from queries while allowing metric probes."""
    metrics: Dict[str, Any] = {
        "k": 5,
        "hit_rate": hit_rate,
        "hit_rate_at_5": hit_rate,
        "mrr": mrr,
        "cases": len(queries),
        "answerable": sum(q["status"] == "scored" for q in queries),
        "unanswerable": sum(q["status"] == "unanswerable" for q in queries),
        "errors": sum(q["status"] == "error" for q in queries),
        "failed_by_id": [q["id"] for q in queries if q["error"]],
        "unanswerable_distractor_leaks": sum(
            q["distractor_leak"] is True for q in queries
        ),
    }
    return {
        "schema": "indexed.eval.report.v1",
        "generated_at": "2026-10-26T00:00:00+00:00",
        "corpus": {
            "tree_sha256": sha256(corpus.encode()).hexdigest(),
            "source_repo_rev": "rev",
            "files": [],
        },
        "case_set": {
            "sha256": sha256(cases.encode()).hexdigest(),
            "path": "cases.json",
            "cases": len(queries),
        },
        "config": {
            "engine": "2",
            "embedding_model": "m1",
            "score_kind": "cosine",
            "rerank": False,
            "top_k": 5,
            "max_docs": 10,
            **(config or {}),
        },
        "environment": {
            "python": "3.13",
            "platform": "test",
            "indexed_version": "test",
            "embedding_model_cache": {
                "cache_dir": "/cache",
                "present": True,
                "weights": ["model.safetensors"],
            },
        },
        "failures": [
            {"id": q["id"], "error": q["error"]} for q in queries if q["error"]
        ],
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
    """Prevent equal metrics from authorizing comparison across different corpus bytes."""
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
    """Prevent equal metrics from hiding a change to the judged questions."""
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
    baseline = _report([_query("a", 1), _unanswerable(False)], hit_rate=1.0, mrr=1.0)
    candidate = _report([_query("a", 1), _unanswerable(True)], hit_rate=1.0, mrr=1.0)
    result = compare_reports(baseline, candidate)
    assert result["verdict"] == VERDICT_REGRESSED
    assert result["metrics"]["delta"]["unanswerable_distractor_leaks"] == 1.0
    assert "distractor_leak 0 -> 1" in format_summary(result)


def test_a_leak_decrease_is_an_improvement() -> None:
    baseline = _report([_query("a", 1), _unanswerable(True)], hit_rate=1.0, mrr=1.0)
    candidate = _report([_query("a", 1), _unanswerable(False)], hit_rate=1.0, mrr=1.0)
    assert compare_reports(baseline, candidate)["verdict"] == VERDICT_IMPROVED


def test_a_different_environment_is_reported_not_hidden() -> None:
    """Same corpus/cases/config, different interpreter — say why the ranks moved."""
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    baseline["environment"].update(python="3.13.5", platform="Linux-arm64")
    candidate = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    candidate["environment"].update(python="3.13.17", platform="Linux-x86_64")
    result = compare_reports(baseline, candidate)
    assert result["verdict"] == VERDICT_UNCHANGED
    assert result["environment_changes"]["python"] == {
        "baseline": "3.13.5",
        "candidate": "3.13.17",
    }
    assert "environment platform: Linux-arm64 -> Linux-x86_64" in format_summary(result)


def _unanswerable(leak: bool) -> Dict[str, Any]:
    """Construct an unanswerable record with consistent distractor-leak evidence."""
    record = _query("unanswerable", None)
    record.update(
        relevant=[],
        distractors=["near.md"],
        ranked_docs=["near.md"] if leak else [],
        ranking=[
            {
                "rank": 1,
                "doc": "near.md",
                "chunk": 0,
                "score": 0.9,
                "score_kind": "cosine",
            }
        ]
        if leak
        else [],
        status="unanswerable",
        distractor_leak=leak,
    )
    return record


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("case_set", "cases", 99),
        ("case_set", "sha256", None),
        ("corpus", "tree_sha256", ""),
        ("config", "rerank", None),
        ("config", "top_k", True),
        ("config", "max_docs", "10"),
        ("metrics", "cases", 99),
        ("metrics", "answerable", 2),
        ("metrics", "unanswerable", 1),
        ("metrics", "errors", 1),
        ("metrics", "failed_by_id", ["a"]),
        ("metrics", "unanswerable_distractor_leaks", 1),
        ("metrics", "hit_rate", float("nan")),
    ],
)
def test_invalid_report_claim_is_incomparable(section, key, value) -> None:
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    candidate = deepcopy(baseline)
    candidate[section][key] = value
    assert exit_code(compare_reports(baseline, candidate)) == 2


@pytest.mark.parametrize(
    "key", ["engine", "embedding_model", "score_kind", "rerank", "top_k", "max_docs"]
)
def test_missing_configuration_field_is_incomparable(key) -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    del report["config"][key]
    assert exit_code(compare_reports(report, report)) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("first_relevant_rank", 2),
        ("reciprocal_rank", 0.5),
        ("hit_at_k", 0.0),
        ("status", "error"),
        ("error", "failure"),
        ("distractor_leak", True),
        ("ranked_docs", ["other.md"]),
        ("relevant", "target.md"),
        ("id", ""),
    ],
)
def test_saved_case_claim_must_match_its_ranking(field, value) -> None:
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    candidate = deepcopy(baseline)
    candidate["queries"][0][field] = value
    assert exit_code(compare_reports(baseline, candidate)) == 2


@pytest.mark.parametrize(
    "value", [None, [], 3, "report", {"schema": "indexed.eval.report.v1"}]
)
def test_malformed_report_returns_incomparable(value) -> None:
    assert exit_code(compare_reports(value, value)) == 2


@pytest.mark.parametrize("value", [None, [], "bad", [None], [{}]])
def test_malformed_query_container_returns_incomparable(value) -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    report["queries"] = value
    assert exit_code(compare_reports(report, report)) == 2


@pytest.mark.parametrize("tolerance", [-1, float("nan"), float("inf"), float("-inf")])
def test_invalid_tolerance_is_incomparable(tolerance) -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    assert exit_code(compare_reports(report, report, tolerance=tolerance)) == 2


def test_missing_baseline_query_is_incomparable() -> None:
    baseline = _report([_query("a", 1), _query("b", 1)], hit_rate=1.0, mrr=1.0)
    candidate = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    assert exit_code(compare_reports(baseline, candidate)) == 2


def test_renamed_query_is_incomparable() -> None:
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    candidate = _report([_query("b", 1)], hit_rate=1.0, mrr=1.0)
    assert exit_code(compare_reports(baseline, candidate)) == 2


def test_duplicate_query_ids_are_incomparable() -> None:
    report = _report([_query("a", 1), _query("a", 1)], hit_rate=1.0, mrr=1.0)
    assert exit_code(compare_reports(report, report)) == 2


def test_failure_summary_must_match_error_records() -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    report["failures"] = [{"id": "a", "error": "invented"}]
    assert exit_code(compare_reports(report, report)) == 2


def test_saved_distractor_leak_must_match_ranked_docs() -> None:
    report = _report([_query("a", 1), _unanswerable(True)], hit_rate=1.0, mrr=1.0)
    report["queries"][1]["distractor_leak"] = False
    assert exit_code(compare_reports(report, report)) == 2


def test_committed_baseline_compares_to_itself() -> None:
    import json

    report = json.loads(Path("eval/baseline.json").read_text())
    assert compare_reports(report, report)["verdict"] == VERDICT_UNCHANGED


@pytest.mark.parametrize(
    "section", ["corpus", "case_set", "config", "metrics", "environment"]
)
@pytest.mark.parametrize("value", [None, [], "bad"])
def test_report_sections_require_objects(section, value) -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    report[section] = value
    assert exit_code(compare_reports(report, report)) == 2


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "query",
        "provenance",
        "rationale",
        "ranked_docs",
        "ranking",
        "relevant",
        "distractors",
        "k",
        "elapsed_ms",
        "error",
        "status",
        "first_relevant_rank",
        "reciprocal_rank",
        "hit_at_k",
        "distractor_leak",
    ],
)
def test_saved_case_requires_complete_evidence(field) -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    del report["queries"][0][field]
    assert exit_code(compare_reports(report, report)) == 2


@pytest.mark.parametrize(
    "field,value",
    [("score", float("inf")), ("rank", 7), ("chunk", "0"), ("doc", "wrong.md")],
)
def test_ranking_details_are_validated(field, value) -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    report["queries"][0]["ranking"][0][field] = value
    assert exit_code(compare_reports(report, report)) == 2


def test_additional_effective_config_field_changes_comparability() -> None:
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    candidate = deepcopy(baseline)
    candidate["config"]["rerank_model"] = "cross-encoder/model"
    result = compare_reports(baseline, candidate)
    assert exit_code(result) == 2
    assert (
        result["config_changes"]["rerank_model"]["candidate"] == "cross-encoder/model"
    )


def test_absent_config_field_differs_from_explicit_null() -> None:
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    candidate = deepcopy(baseline)
    candidate["config"]["optional_knob"] = None
    assert exit_code(compare_reports(baseline, candidate)) == 2


@pytest.mark.parametrize(
    "section,key", [("case_set", "sha256"), ("corpus", "tree_sha256")]
)
def test_missing_experiment_hash_is_incomparable(section, key) -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    del report[section][key]
    assert exit_code(compare_reports(report, report)) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("python", []),
        ("platform", None),
        ("indexed_version", 3),
        ("embedding_model_cache", None),
    ],
)
def test_environment_fields_have_declared_types(field, value) -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    report["environment"][field] = value
    assert exit_code(compare_reports(report, report)) == 2


def test_large_finite_integer_input_does_not_crash_validation() -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    report["queries"][0]["ranking"][0]["score"] = 10**400
    assert compare_reports(report, report)["verdict"] == VERDICT_UNCHANGED


@pytest.mark.parametrize("chunks", [None, [{}], [{"chunkNumber": None}]])
def test_producer_optional_chunk_sentinel_compares_unchanged(chunks) -> None:
    """Keep producer document-only chunk sentinels valid through report comparison."""
    from indexed.eval.cases import Case
    from indexed.eval.runner import RunConfig, _case_record

    entry = {"id": "target.md"}
    if chunks is not None:
        entry["matchedChunks"] = chunks
    case = Case("a", "query", "issue title", "target answers", ["target.md"])
    record = _case_record(case, {"eval-corpus": {"results": [entry]}}, RunConfig(), 1.0)
    assert record["ranking"][0]["chunk"] == -1
    report = _report([record], hit_rate=1.0, mrr=1.0)
    assert compare_reports(report, report)["verdict"] == VERDICT_UNCHANGED


@pytest.mark.parametrize("chunk", [-2, -3, True, False])
def test_invalid_chunk_values_remain_incomparable(chunk) -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    report["queries"][0]["ranking"][0]["chunk"] = chunk
    assert exit_code(compare_reports(report, report)) == 2


def test_changed_shared_judgment_cannot_fabricate_improvement() -> None:
    baseline = _report([_query("a", 2)], hit_rate=1.0, mrr=0.5)
    candidate = deepcopy(baseline)
    candidate["queries"][0].update(
        relevant=["other-1.md"], first_relevant_rank=1, reciprocal_rank=1.0
    )
    candidate["metrics"]["mrr"] = 1.0
    assert exit_code(compare_reports(baseline, candidate)) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("query", "different query"),
        ("distractors", ["near.md"]),
        ("provenance", "different issue"),
        ("rationale", "different evidence"),
        ("answered_by", "target.md:4"),
    ],
)
def test_shared_case_identity_and_judgments_are_immutable(field, value) -> None:
    """Refuse comparisons that silently change the meaning of a shared case ID."""
    baseline = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    candidate = deepcopy(baseline)
    candidate["queries"][0][field] = value
    result = compare_reports(baseline, candidate)
    assert exit_code(result) == 2
    assert any(field in reason for reason in result["incomparable_reasons"])


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "container", [lambda x: x, lambda x: {"nested": x}, lambda x: [{"nested": [x]}]]
)
def test_all_effective_config_numbers_must_be_finite(number, container) -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    report["config"]["additional_setting"] = container(number)
    assert exit_code(compare_reports(report, report)) == 2


def test_finite_additive_config_values_remain_supported() -> None:
    report = _report([_query("a", 1)], hit_rate=1.0, mrr=1.0)
    report["config"]["additional_setting"] = {"nested": [0.5, 2, None, True, "model"]}
    assert compare_reports(report, report)["verdict"] == VERDICT_UNCHANGED
