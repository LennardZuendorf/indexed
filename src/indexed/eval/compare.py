"""Compare a fresh eval report against the committed baseline (issue #204).

The whole point of the harness is this call: it answers "did that retrieval
change actually help?" with a verdict, not a vibe. It compares only reports it
can honestly compare — a different corpus tree or a different case set is a
different experiment, and is reported as ``comparable: false`` rather than as an
improvement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from indexed.eval.metrics import aggregate

COMPARE_SCHEMA = "indexed.eval.compare.v1"
REPORT_SCHEMA = "indexed.eval.report.v1"

#: Absolute metric deltas smaller than this are noise, not movement.
DEFAULT_TOLERANCE = 0.0

VERDICT_IMPROVED = "improved"
VERDICT_REGRESSED = "regressed"
VERDICT_UNCHANGED = "unchanged"
VERDICT_INCOMPARABLE = "incomparable"


def _metric(report: Dict[str, Any], name: str) -> Optional[float]:
    """A metric value, or ``None`` when the report holds no measurement."""
    value = (report.get("metrics") or {}).get(name)
    return None if value is None else float(value)


def _by_id(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {record["id"]: record for record in report.get("queries") or []}


def _environment_value(report: Dict[str, Any], key: str) -> Optional[str]:
    """One environment field, or ``None`` when the report did not record it."""
    value = (report.get("environment") or {}).get(key)
    return None if value is None else str(value)


def report_problems(report: Dict[str, Any], label: str) -> List[str]:
    """Why a report cannot be trusted as a measurement, if anything."""
    problems: List[str] = []
    if report.get("schema") != REPORT_SCHEMA:
        problems.append(
            f"{label} is not a {REPORT_SCHEMA} report (schema={report.get('schema')!r})"
        )
    metrics = report.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        problems.append(f"{label} carries no metrics")
    if not isinstance(report.get("queries"), list):
        problems.append(f"{label} carries no per-case records")
    if not isinstance(report.get("corpus"), dict):
        problems.append(f"{label} names no corpus revision")
    if not isinstance(report.get("case_set"), dict):
        problems.append(f"{label} names no case-set revision")
    return problems


def _recomputed_metrics(report: Dict[str, Any], k: int) -> Dict[str, Any]:
    """Metrics recomputed from the per-case records (the report's own evidence)."""
    return aggregate(report.get("queries") or [], k)


def compare_reports(
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> Dict[str, Any]:
    """Diff two reports: metric deltas, per-query rank movement, verdict.

    ``tolerance`` is an absolute delta below which a metric counts as unchanged.
    Pick it from observed baseline noise once there is more than one baseline run
    — not from a percentage that sounds rigorous (#205 makes the same point).

    A report is only comparable to another when they measured the same corpus
    tree, the same case set, and the same retrieval configuration: a model swap
    or a ``max_docs`` change moves the numbers without being a ranking win.
    """
    reasons: List[str] = report_problems(baseline, "baseline")
    reasons.extend(report_problems(candidate, "candidate"))

    baseline_corpus = (baseline.get("corpus") or {}).get("tree_sha256")
    candidate_corpus = (candidate.get("corpus") or {}).get("tree_sha256")
    baseline_cases = (baseline.get("case_set") or {}).get("sha256")
    candidate_cases = (candidate.get("case_set") or {}).get("sha256")

    if baseline_corpus != candidate_corpus:
        reasons.append(f"corpus tree differs ({baseline_corpus} != {candidate_corpus})")
    if baseline_cases != candidate_cases:
        reasons.append(f"case set differs ({baseline_cases} != {candidate_cases})")

    baseline_metrics = baseline.get("metrics") or {}
    candidate_metrics = candidate.get("metrics") or {}
    if baseline_metrics.get("k") != candidate_metrics.get("k"):
        reasons.append(
            f"hit-rate cut differs (k {baseline_metrics.get('k')} != "
            f"{candidate_metrics.get('k')})"
        )

    baseline_config = baseline.get("config") or {}
    candidate_config = candidate.get("config") or {}
    config_changes = {
        key: {
            "baseline": baseline_config.get(key),
            "candidate": candidate_config.get(key),
        }
        for key in sorted(set(baseline_config) | set(candidate_config))
        if baseline_config.get(key) != candidate_config.get(key)
    }
    for key in config_changes:
        reasons.append(f"config {key} differs")

    hit_before = _metric(baseline, "hit_rate")
    hit_after = _metric(candidate, "hit_rate")
    mrr_before = _metric(baseline, "mrr")
    mrr_after = _metric(candidate, "mrr")
    leak_before = _metric(baseline, "unanswerable_distractor_leaks")
    leak_after = _metric(candidate, "unanswerable_distractor_leaks")
    if hit_before is None or mrr_before is None:
        reasons.append("baseline has no measured metric (no answerable case scored)")
    if hit_after is None or mrr_after is None:
        reasons.append("candidate has no measured metric (no answerable case scored)")

    # A report whose headline numbers disagree with its own per-case records was
    # edited, not measured.
    for label, report, metrics in (
        ("baseline", baseline, baseline_metrics),
        ("candidate", candidate, candidate_metrics),
    ):
        if isinstance(metrics.get("k"), int) and isinstance(
            report.get("queries"), list
        ):
            rebuilt = _recomputed_metrics(report, metrics["k"])
            if (rebuilt["hit_rate"], rebuilt["mrr"]) != (
                metrics.get("hit_rate"),
                metrics.get("mrr"),
            ):
                reasons.append(f"{label} metrics contradict its per-case records")

    deltas = {
        "hit_rate": (
            None
            if hit_before is None or hit_after is None
            else round(hit_after - hit_before, 6)
        ),
        "mrr": (
            None
            if mrr_before is None or mrr_after is None
            else round(mrr_after - mrr_before, 6)
        ),
    }

    before_cases = _by_id(baseline)
    after_cases = _by_id(candidate)
    improved: List[Dict[str, Any]] = []
    regressed: List[Dict[str, Any]] = []
    newly_failed: List[str] = []

    for case_id in sorted(set(before_cases) | set(after_cases)):
        before = before_cases.get(case_id)
        after = after_cases.get(case_id)
        if before is None or after is None:
            if after is not None and after.get("error"):
                newly_failed.append(case_id)
            continue
        if after.get("error") and not before.get("error"):
            newly_failed.append(case_id)
        before_rr = float(before.get("reciprocal_rank") or 0.0)
        after_rr = float(after.get("reciprocal_rank") or 0.0)
        move = round(after_rr - before_rr, 6)
        if move > tolerance:
            improved.append(
                {
                    "id": case_id,
                    "rank_before": before.get("first_relevant_rank"),
                    "rank_after": after.get("first_relevant_rank"),
                }
            )
        elif move < -tolerance:
            regressed.append(
                {
                    "id": case_id,
                    "rank_before": before.get("first_relevant_rank"),
                    "rank_after": after.get("first_relevant_rank"),
                }
            )

    leak_delta = (
        None
        if leak_before is None or leak_after is None
        else round(leak_after - leak_before, 6)
    )

    # Same corpus, same cases, same config — but a different interpreter or CPU
    # build still produces different embedding floats and therefore a different
    # ranking. The baseline is a measurement of one environment; say so instead of
    # letting a cross-environment diff read as a ranking change.
    environment_changes = {
        key: {
            "baseline": _environment_value(baseline, key),
            "candidate": _environment_value(candidate, key),
        }
        for key in ("python", "platform")
        if _environment_value(baseline, key) != _environment_value(candidate, key)
    }

    if reasons:
        verdict = VERDICT_INCOMPARABLE
    elif (
        newly_failed
        or regressed
        or (leak_delta is not None and leak_delta > 0)
        or any(delta < -tolerance for delta in deltas.values() if delta)
    ):
        # A compensating pair (one case up, one case down) nets to a zero metric
        # delta; the per-case regression is still a regression, so it decides the
        # verdict instead of sitting in a list the exit code never reads.
        verdict = VERDICT_REGRESSED
    elif (leak_delta is not None and leak_delta < 0) or any(
        delta > tolerance for delta in deltas.values() if delta
    ):
        verdict = VERDICT_IMPROVED
    else:
        verdict = VERDICT_UNCHANGED

    return {
        "schema": COMPARE_SCHEMA,
        "verdict": verdict,
        "comparable": not reasons,
        "incomparable_reasons": reasons,
        "tolerance": tolerance,
        "baseline": {
            "generated_at": baseline.get("generated_at"),
            "corpus_tree": baseline_corpus,
            "case_set": baseline_cases,
        },
        "candidate": {
            "generated_at": candidate.get("generated_at"),
            "corpus_tree": candidate_corpus,
            "case_set": candidate_cases,
        },
        "config_changes": config_changes,
        "environment_changes": environment_changes,
        "metrics": {
            "baseline": {
                "hit_rate": hit_before,
                "mrr": mrr_before,
                "unanswerable_distractor_leaks": leak_before,
            },
            "candidate": {
                "hit_rate": hit_after,
                "mrr": mrr_after,
                "unanswerable_distractor_leaks": leak_after,
            },
            "delta": {**deltas, "unanswerable_distractor_leaks": leak_delta},
        },
        "improved": improved,
        "regressed": regressed,
        "newly_failed": newly_failed,
    }


def format_summary(result: Dict[str, Any]) -> str:
    """One-screen human summary of a comparison (plain text, no markup)."""
    lines = [f"verdict: {result['verdict']}"]
    if not result["comparable"]:
        for reason in result["incomparable_reasons"]:
            lines.append(f"  not comparable: {reason}")
    baseline_metrics = result["metrics"]["baseline"]
    candidate_metrics = result["metrics"]["candidate"]
    delta = result["metrics"]["delta"]
    for name, label in (("hit_rate", "hit_rate"), ("mrr", "mrr     ")):
        before = baseline_metrics[name]
        after = candidate_metrics[name]
        if before is None or after is None:
            lines.append(f"  {label} n/a (no answerable case scored)")
        else:
            lines.append(
                "  {} {:.3f} -> {:.3f} ({:+.3f})".format(
                    label, before, after, delta[name]
                )
            )
    for change, values in result["config_changes"].items():
        lines.append(
            f"  config {change}: {values['baseline']} -> {values['candidate']}"
        )
    leak_before = baseline_metrics.get("unanswerable_distractor_leaks")
    leak_after = candidate_metrics.get("unanswerable_distractor_leaks")
    if leak_before is not None and leak_after is not None:
        lines.append(
            f"  distractor_leak {leak_before:g} -> {leak_after:g} (lower is better)"
        )
    for key, values in result.get("environment_changes", {}).items():
        lines.append(
            f"  environment {key}: {values['baseline']} -> {values['candidate']} "
            "(a different interpreter/build moves the numbers; the baseline is "
            "one environment's measurement)"
        )
    for case in result["improved"]:
        lines.append(
            f"  improved {case['id']}: rank {case['rank_before']} -> {case['rank_after']}"
        )
    for case in result["regressed"]:
        lines.append(
            f"  regressed {case['id']}: rank {case['rank_before']} -> {case['rank_after']}"
        )
    for case_id in result["newly_failed"]:
        lines.append(f"  newly failed: {case_id}")
    return "\n".join(lines)


def exit_code(result: Dict[str, Any]) -> int:
    """0 clean/improved, 1 regressed, 2 not comparable — CI-friendly."""
    if result["verdict"] == VERDICT_INCOMPARABLE:
        return 2
    if result["verdict"] == VERDICT_REGRESSED:
        return 1
    return 0


def load_report(path: str) -> Dict[str, Any]:
    """Load a saved report; the caller owns the parse error."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
