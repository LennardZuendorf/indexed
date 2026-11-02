#!/usr/bin/env python3
"""Same-job A/B comparator for the PR benchmark and retrieval gates.

Reads two measurement files taken back to back on one runner — the merge base
(``origin/<base ref>``) and the PR head — and turns their ratio into the gate's
only verdict. No committed baseline is read here: a cross-run number carries the
machine that produced it, so it can report drift but cannot decide a PR
(.spec/tech.md § CI Benchmarking).

Two shapes are accepted, because both gates answer the same question:

* **pytest-benchmark results** (``benchmarks``) — seconds, lower is better, and
  the tolerance is a percentage of the merge base.
* **``indexed.eval.report.v1``** retrieval reports — hit-rate@k and MRR, higher
  is better, and the tolerance is an absolute metric delta.

Two failure modes are kept apart on purpose:

* **a regression** — the head is worse than its own merge base past tolerance.
  That is a verdict, and the gate fails.
* **an invalid measurement** — the two files disagree on machine fingerprint,
  interpreter, corpus tree, case set or retrieval configuration, so the
  comparison measures the harness rather than the diff. That is a bug to fix,
  not a verdict to record, so it exits with its own code and message.

Usage::

    python scripts/benchmark_ab.py --base base.json --head head.json \\
        --tolerance 20 --summary "$GITHUB_STEP_SUMMARY"

    python scripts/benchmark_ab.py --base base.json --head head.json \\
        --tolerance 0.02 --out eval-ab.json

    python scripts/benchmark_ab.py --spread run1.json run2.json run3.json

Exit codes: 0 pass, 1 regression, 2 measurement invalid (or unusable input).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

PASS_EXIT = 0
REGRESSION_EXIT = 1
INVALID_EXIT = 2

BENCHMARK_SHAPE = "pytest-benchmark"
EVAL_SHAPE = "indexed-eval"

#: Absolute retrieval-metric delta treated as noise, in metric points.
#:
#: Measured, not tasted. Three repeats of the head tree in one CI job were
#: identical (spread 0.000 on hit-rate@5 and MRR, zero rank differences), so
#: repeat-to-repeat noise is zero. The larger term is the base/head boundary:
#: the base is measured in its own worktree and venv, and on PR #274 — whose
#: diff cannot move retrieval at all — MRR differed by 0.0307 while hit@5
#: stayed 1.0 (base 0.8070, head 0.8377; run 41422911438). 0.04 covers that
#: 0.0307 plus a margin and stays under one case of the 19 answerable ones
#: (1/19 = 0.0526 of hit@5), so a single case falling out of the top 5 still
#: fails the gate. Raise it only with a new measurement recorded here.
EVAL_TOLERANCE = 0.04

#: Retrieval metrics the gate decides on. Leaks stay report-only (issue #204).
EVAL_GATE_METRICS = ("hit_rate", "mrr")

#: Direction of each retrieval metric: higher is better, leaks are lower.
EVAL_METRIC_DIRECTION = {
    "hit_rate": True,
    "hit_rate_at_5": True,
    "mrr": True,
    "unanswerable_distractor_leaks": False,
}


class MeasurementInvalid(Exception):
    """The two result files cannot be compared; there is no verdict to give."""


@dataclass
class Row:
    """One measurement, as taken on both sides of the A/B."""

    name: str
    base: float
    head: float
    higher_is_better: bool = False
    gating: bool = True

    @property
    def delta(self) -> float:
        """Head minus base, in the metric's own unit."""
        return self.head - self.base

    @property
    def change_pct(self) -> float:
        """Relative change; positive is slower for a duration benchmark."""
        return (self.head - self.base) / self.base * 100.0

    def worse_by(self, unit: str) -> float:
        """How far the head moved the wrong way, in the tolerance's unit."""
        if unit == "points":
            return -self.delta if self.higher_is_better else self.delta
        return self.change_pct


@dataclass
class Result:
    """Everything the caller needs to print, summarise and exit on."""

    rows: list[Row] = field(default_factory=list)
    regressions: list[Row] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    cases: list[dict[str, Any]] = field(default_factory=list)
    shape: str = BENCHMARK_SHAPE
    stat: str = "min"
    unit: str = "pct"

    @property
    def gating_rows(self) -> list[Row]:
        return [row for row in self.rows if row.gating]

    def decide(self, tolerance: float) -> None:
        """Split the gating rows into within-tolerance and over-tolerance."""
        self.regressions = [
            row for row in self.gating_rows if row.worse_by(self.unit) > tolerance
        ]


def shape(doc: dict) -> str:
    """Which gate produced this file."""
    if str(doc.get("schema", "")).startswith("indexed.eval.report"):
        return EVAL_SHAPE
    if isinstance(doc.get("benchmarks"), list):
        return BENCHMARK_SHAPE
    raise MeasurementInvalid(
        "one of the two files is neither a pytest-benchmark result nor an "
        "indexed eval report, so there is nothing to compare."
    )


def _machine(doc: dict) -> dict:
    """Machine block of either shape, in pytest-benchmark's layout.

    Retrieval reports record the same block under ``environment.machine`` so one
    fingerprint function serves both gates.
    """
    info = doc.get("machine_info")
    if isinstance(info, dict):
        return info
    environment = doc.get("environment")
    if isinstance(environment, dict) and isinstance(environment.get("machine"), dict):
        return environment["machine"]
    return {}


def fingerprint(doc: dict) -> str:
    """CPU fingerprint of the machine that produced a result file.

    Matches the identity each workflow prints: CPU model, architecture, core
    count, OS. ``?`` stands in for a missing field so two equally broken files
    still compare equal-or-not honestly. Reports from before the machine block
    existed fall back to their platform string.
    """
    info = _machine(doc)
    cpu = info.get("cpu") or {}
    parts = [
        cpu.get("brand_raw"),
        cpu.get("arch"),
        cpu.get("count"),
        info.get("system"),
    ]
    if all(part is None for part in parts):
        return str((doc.get("environment") or {}).get("platform", "?"))
    return "|".join("?" if part is None else str(part) for part in parts)


def interpreter(doc: dict) -> str:
    """Python version that produced a result file."""
    return str(
        _machine(doc).get("python_version")
        or (doc.get("environment") or {}).get("python")
        or "?"
    )


def host_fingerprint() -> str:
    """Fingerprint of the machine running this process, in the report's shape.

    The job that measures both sides knows its own machine; printing that once
    (and validating any recorded ``environment.machine`` against it) is how the
    gate proves both measurements ran here rather than merely asserting it.
    """
    brand = "?"
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                brand = line.split(":", 1)[1].strip()
                break
    except (OSError, IndexError):
        brand = platform.processor() or "?"
    return "|".join([brand, platform.machine(), str(os.cpu_count()), platform.system()])


def adopt_host_machine(doc: dict, host: str) -> str | None:
    """Stamp this job's machine into a report that predates the machine block.

    Reports written before ``environment.machine`` existed (any merge base from
    a commit older than this feature) cannot name their own host. The job can:
    it measured this side on this runner minutes ago. Adoption is not a free
    pass — it happens only when the report's recorded ``platform`` string is
    the running machine's, which a report copied from another host fails. An
    explicit machine block is never overwritten; a disagreement is invalid.
    """
    if _machine(doc) or not host:
        return None
    parts = host.split("|")
    if len(parts) != 4:
        raise MeasurementInvalid(
            f"the job fingerprint {host!r} is not brand|arch|count|system."
        )
    brand, arch, count, system = parts
    environment = doc.get("environment") or {}
    recorded = environment.get("platform")
    current = platform.platform()
    if recorded != current:
        raise MeasurementInvalid(
            f"a report has no machine block and its platform {recorded!r} is not "
            f"this job's {current!r}. Same-job measurement invalid — that "
            "report was not produced on this machine."
        )
    try:
        cpu_count = int(count)
    except ValueError as exc:
        raise MeasurementInvalid(
            f"the job fingerprint {host!r} carries a non-integer core count."
        ) from exc
    doc.setdefault("environment", {})["machine"] = {
        "cpu": {"brand_raw": brand, "arch": arch, "count": cpu_count},
        "system": system,
    }
    return (
        f"a report predates environment.machine; adopted this job's "
        f"fingerprint {host} after its platform string matched this machine."
    )


def _check_same_machine(
    base_doc: dict, head_doc: dict, host: str | None = None
) -> None:
    """Refuse to turn a machine mismatch into a verdict: that is a harness bug."""
    was, now = fingerprint(base_doc), fingerprint(head_doc)
    if host:
        for side, doc, seen in (
            ("merge base", base_doc, was),
            ("head", head_doc, now),
        ):
            if _machine(doc) and seen != host:
                raise MeasurementInvalid(
                    f"the {side} report records {seen}, but this job runs on "
                    f"{host}. Same-job measurement invalid — one side was "
                    "measured somewhere else, so the ratio is not a verdict."
                )
    if was != now:
        raise MeasurementInvalid(
            f"the merge base was measured on {was}, the head on {now}. "
            "Same-job measurement invalid — this is a harness bug, not a verdict."
        )
    base_py, head_py = interpreter(base_doc), interpreter(head_doc)
    if base_py != head_py:
        raise MeasurementInvalid(
            f"the merge base was measured with Python {base_py}, the head with "
            f"Python {head_py}. Same-job measurement invalid — numbers from "
            "different interpreters are not comparable."
        )


def samples(doc: dict, stat: str = "min") -> dict[str, float]:
    """Map benchmark full name -> ``stat`` seconds for one result file.

    The default is the minimum, not the mean: tenancy noise only ever *adds*
    time to a round, so the best observed round is the most stable estimator of
    the code's own cost. On unchanged code measured locally, means disagreed by
    up to 20 % (one slow round in a 3-round benchmark), medians by 12 %, and
    minimums by 0.7 %. A real regression moves the minimum too; noise does not.
    """
    out: dict[str, float] = {}
    for bench in doc.get("benchmarks") or []:
        name = bench.get("fullname") or bench.get("name")
        value = (bench.get("stats") or {}).get(stat)
        if name is not None and value is not None:
            out[str(name)] = float(value)
    return out


def _benchmark_result(base_doc: dict, head_doc: dict, stat: str) -> Result:
    """Pair the two benchmark files and keep only same-code rows."""
    base_rows, head_rows = samples(base_doc, stat), samples(head_doc, stat)
    result = Result(shape=BENCHMARK_SHAPE, unit="pct", stat=stat)
    for name in sorted(set(base_rows) | set(head_rows)):
        if name not in head_rows:
            result.skipped.append(name)
            result.warnings.append(
                f"{name} was measured on the merge base only — not compared."
            )
            continue
        if name not in base_rows:
            result.skipped.append(name)
            result.warnings.append(
                f"{name} was measured on the head only — not compared."
            )
            continue
        if base_rows[name] <= 0:
            result.skipped.append(name)
            result.warnings.append(
                f"{name} has a non-positive merge-base {stat} ({base_rows[name]}) — not compared."
            )
            continue
        result.rows.append(Row(name, base_rows[name], head_rows[name]))
    if not result.rows:
        raise MeasurementInvalid(
            "the two result files share no comparable benchmark rows, so the "
            "A/B measured nothing. Same-job measurement invalid — this is a "
            "harness bug, not a verdict."
        )
    return result


def _eval_config(report: dict) -> dict:
    """Retrieval configuration, without the fields that record what was measured."""
    config = dict(report.get("config") or {})
    for key in ("embedding_model", "score_kind"):
        config.pop(key, None)
    return config


def _check_same_experiment(base_doc: dict, head_doc: dict) -> None:
    """Refuse to compare two different experiments: only the diff may differ.

    A corpus, case-set or retrieval-configuration change is a different
    measurement, not a better or worse one. Calling it a regression (or a pass)
    would be the same class of lie as comparing two machines.
    """
    base_corpus = (base_doc.get("corpus") or {}).get("tree_sha256")
    head_corpus = (head_doc.get("corpus") or {}).get("tree_sha256")
    if base_corpus != head_corpus:
        raise MeasurementInvalid(
            f"the pinned corpus differs ({str(base_corpus)[:12]} -> "
            f"{str(head_corpus)[:12]}). Same-job measurement invalid — a corpus "
            "change is a different experiment, not a verdict on this diff."
        )
    base_cases = (base_doc.get("case_set") or {}).get("sha256")
    head_cases = (head_doc.get("case_set") or {}).get("sha256")
    if base_cases != head_cases:
        raise MeasurementInvalid(
            f"the pinned case set differs ({str(base_cases)[:12]} -> "
            f"{str(head_cases)[:12]}). Same-job measurement invalid — a case-set "
            "change is a different experiment, not a verdict on this diff."
        )
    base_config, head_config = _eval_config(base_doc), _eval_config(head_doc)
    changed = sorted(
        key
        for key in set(base_config) | set(head_config)
        if base_config.get(key) != head_config.get(key)
    )
    if changed:
        pairs = ", ".join(
            f"{key} {base_config.get(key)!r} -> {head_config.get(key)!r}"
            for key in changed
        )
        raise MeasurementInvalid(
            f"the retrieval configuration differs ({pairs}). Same-job measurement "
            "invalid — a configuration change is a different experiment, not a "
            "verdict on this diff."
        )


def _metric(report: dict, name: str) -> float | None:
    value = (report.get("metrics") or {}).get(name)
    return None if value is None else float(value)


def _eval_rows(base_doc: dict, head_doc: dict, metrics: Iterable[str]) -> list[Row]:
    """One row per gating metric, plus a report-only row for the leak count."""
    wanted = list(metrics)
    names = wanted + [
        name
        for name in ("unanswerable_distractor_leaks",)
        if name not in wanted and _metric(base_doc, name) is not None
    ]
    rows: list[Row] = []
    for name in names:
        before, after = _metric(base_doc, name), _metric(head_doc, name)
        if before is None or after is None:
            continue
        rows.append(
            Row(
                name=name,
                base=before,
                head=after,
                higher_is_better=EVAL_METRIC_DIRECTION.get(name, True),
                gating=name in wanted,
            )
        )
    return rows


def _case_movement(base_doc: dict, head_doc: dict) -> list[dict[str, Any]]:
    """Per-case rank movement, so the PR comment can show what actually moved."""

    def ranks(report: dict) -> dict[str, Any]:
        return {
            str(record.get("id")): record.get("first_relevant_rank")
            for record in report.get("queries") or []
        }

    before, after = ranks(base_doc), ranks(head_doc)
    return [
        {
            "id": case_id,
            "rank_before": before[case_id],
            "rank_after": after[case_id],
        }
        for case_id in sorted(set(before) & set(after))
        if before[case_id] != after[case_id]
    ]


def compare(
    base_doc: dict,
    head_doc: dict,
    *,
    stat: str = "min",
    metrics: Iterable[str] = EVAL_GATE_METRICS,
    host: str | None = None,
) -> Result:
    """Pair two measurements from one job into rows, or say why there is no verdict."""
    base_shape, head_shape = shape(base_doc), shape(head_doc)
    if base_shape != head_shape:
        raise MeasurementInvalid(
            f"the merge base is a {base_shape} file, the head a {head_shape} "
            "file. Same-job measurement invalid — the two sides measured "
            "different things."
        )
    _check_same_machine(base_doc, head_doc, host)

    if base_shape == EVAL_SHAPE:
        _check_same_experiment(base_doc, head_doc)
        result = Result(
            shape=EVAL_SHAPE,
            unit="points",
            stat="metric",
            rows=_eval_rows(base_doc, head_doc, metrics),
            cases=_case_movement(base_doc, head_doc),
        )
        if not result.rows:
            raise MeasurementInvalid(
                "the two reports share no gating metric, so the A/B measured "
                "nothing. Same-job measurement invalid — this is a harness bug, "
                "not a verdict."
            )
        return result

    return _benchmark_result(base_doc, head_doc, stat)


def table(result: Result) -> str:
    """Fixed-width table: absolute numbers on both sides, then the movement."""
    if result.shape == EVAL_SHAPE:
        lines = [
            f"{'metric':<34} {'base':>10} {'head':>10} {'delta':>10} verdict",
            "-" * 88,
        ]
        for row in result.rows:
            verdict = "report only" if not row.gating else "gate"
            if row in result.regressions:
                verdict = "OVER"
            lines.append(
                f"{row.name:<34} {row.base:>10.4f} {row.head:>10.4f} "
                f"{row.delta:>+10.4f} {verdict}"
            )
        return "\n".join(lines)

    lines = [
        f"{'benchmark':<64} {'base ' + result.stat:>14} "
        f"{'head ' + result.stat:>14} {'change':>9}",
        "-" * 104,
    ]
    for row in result.rows:
        lines.append(
            f"{row.name:<64} {row.base * 1000:>8.2f}ms {row.head * 1000:>8.2f}ms "
            f"{row.change_pct:>+8.1f}%"
        )
    return "\n".join(lines)


def verdict_line(result: Result, tolerance: float) -> str:
    """One line naming the verdict and its unit, printed and summarised alike."""
    if result.regressions:
        worst = max(result.regressions, key=lambda row: row.worse_by(result.unit))
        return (
            f"gate verdict: FAIL ({len(result.regressions)}/{len(result.gating_rows)} "
            f"{result.unit} over {tolerance:g} of the merge base; worst "
            f"{worst.name} {worst.worse_by(result.unit):+.4g})"
        )
    return (
        f"gate verdict: PASS ({len(result.gating_rows)} measurements within "
        f"{tolerance:g} of the merge base, {result.unit})"
    )


def summary_markdown(
    result: Result,
    tolerance: float,
    base_label: str,
    head_label: str,
    base_doc: dict | None = None,
    head_doc: dict | None = None,
) -> str:
    """GitHub job-summary section for the A/B, fingerprints included."""
    title = (
        "## Retrieval gate: same-job A/B"
        if result.shape == EVAL_SHAPE
        else "## Benchmark gate: same-job A/B"
    )
    lines = [
        title,
        "",
        "Both sides measured in this job on this runner, back to back, so the "
        "machine cancels out of the ratio.",
        "",
        "| Side | Revision | Fingerprint |",
        "|---|---|---|",
        f"| merge base | `{base_label}` | `{fingerprint(base_doc) if base_doc else '?'}` |",
        f"| head | `{head_label}` | `{fingerprint(head_doc) if head_doc else '?'}` |",
        "",
    ]
    if result.shape == EVAL_SHAPE:
        lines += [
            f"Comparing hit-rate@k and MRR with an absolute tolerance of "
            f"{tolerance:g} metric points; the distractor-leak count is reported.",
            "",
            "| Metric | Merge base | Head | Delta | Verdict |",
            "|---|---|---|---|---|",
        ]
        for row in result.rows:
            if row in result.regressions:
                verdict = "**over tolerance**"
            else:
                verdict = "within" if row.gating else "report only"
            lines.append(
                f"| `{row.name}` | {row.base:.4f} | {row.head:.4f} "
                f"| {row.delta:+.4f} | {verdict} |"
            )
        if result.cases:
            lines += ["", "<details><summary>Per-case rank movement</summary>", ""]
            for case in result.cases:
                lines.append(
                    f"- `{case['id']}`: rank {case['rank_before']} -> "
                    f"{case['rank_after']}"
                )
            lines.append("</details>")
    else:
        lines += [
            f"Comparing the {result.stat} of each benchmark.",
            "",
            "| Benchmark | Merge base | Head | Change | Verdict |",
            "|---|---|---|---|---|",
        ]
        for row in result.rows:
            verdict = "**over tolerance**" if row in result.regressions else "within"
            lines.append(
                f"| `{row.name}` | {row.base * 1000:.2f} ms | "
                f"{row.head * 1000:.2f} ms | {row.change_pct:+.1f}% | {verdict} |"
            )
    lines.append("")
    if result.regressions:
        lines.append(
            f"**Verdict: FAIL** — {len(result.regressions)} of "
            f"{len(result.gating_rows)} measurements regressed past "
            f"{tolerance:g} against their own merge base."
        )
    else:
        lines.append(
            f"**Verdict: PASS** — {len(result.gating_rows)} measurements within "
            f"{tolerance:g} of their own merge base."
        )
    for warning in result.warnings:
        lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"


def _side(doc: dict, label: str) -> dict[str, Any]:
    """One side of the A/B, as the PR comment and the artifact record it."""
    return {
        "label": label,
        "revision": (doc.get("environment") or {}).get("indexed_git_rev"),
        "fingerprint": fingerprint(doc),
        "interpreter": interpreter(doc),
    }


def result_json(
    result: Result,
    tolerance: float,
    base_doc: dict,
    head_doc: dict,
    base_label: str,
    head_label: str,
) -> dict[str, Any]:
    """Machine-readable A/B for the PR comment (``indexed.eval.ab.v1``)."""
    return {
        "schema": "indexed.eval.ab.v1",
        "kind": result.shape,
        "verdict": "fail" if result.regressions else "pass",
        "tolerance": tolerance,
        "unit": result.unit,
        "base": _side(base_doc, base_label),
        "head": _side(head_doc, head_label),
        "metrics": [
            {
                "name": row.name,
                "base": row.base,
                "head": row.head,
                "delta": row.delta,
                "gating": row.gating,
                "verdict": "over" if row in result.regressions else "within",
            }
            for row in result.rows
        ],
        "cases": result.cases,
        "warnings": result.warnings,
        "invalid_reasons": [],
    }


def spread(paths: list[str]) -> int:
    """Report the run-to-run spread of the gating metrics across repeats.

    Several observations of one tree on one runner are what make a tolerance a
    measurement instead of a preference: the gate's constant has to exceed the
    movement the harness produces on its own.
    """
    docs: list[dict] = []
    try:
        for path in paths:
            docs.append(json.loads(Path(path).read_text()))
    except (OSError, ValueError) as exc:
        print(f"::error title=Variance probe invalid::cannot read a result file: {exc}")
        return INVALID_EXIT
    if len(docs) < 2:
        print("::error title=Variance probe invalid::need at least two runs")
        return INVALID_EXIT
    if len({fingerprint(doc) for doc in docs}) != 1:
        print(
            "::error title=Variance probe invalid::the repeats ran on different machines"
        )
        return INVALID_EXIT

    for name in EVAL_GATE_METRICS:
        values = [value for doc in docs if (value := _metric(doc, name)) is not None]
        if not values:
            print(f"{name:<8} no measurement")
            continue
        print(
            f"{name:<8} spread {max(values) - min(values):.6f} "
            f"({min(values):.4f}..{max(values):.4f} over {len(values)} runs)"
        )

    def ranks(doc: dict) -> dict[str, Any]:
        return {
            str(record.get("id")): record.get("first_relevant_rank")
            for record in doc.get("queries") or []
        }

    every = [ranks(doc) for doc in docs]
    moved = sorted(
        case_id
        for case_id in set().union(*every)
        if len({mapping.get(case_id) for mapping in every}) > 1
    )
    print(f"cases with a rank difference across repeats: {len(moved)}")
    for case_id in moved:
        print(f"  {case_id}: {[mapping.get(case_id) for mapping in every]}")
    return PASS_EXIT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare merge-base and head measurements from one job."
    )
    parser.add_argument("--base", help="merge-base result JSON")
    parser.add_argument("--head", help="head result JSON")
    parser.add_argument(
        "--spread",
        nargs="+",
        metavar="REPORT",
        help="report the run-to-run spread across repeats of one tree instead of gating",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help=(
            "how far the head may move against its own merge base before it is a "
            "regression: percent of the base for benchmarks (default 20), absolute "
            f"metric points for retrieval reports (default {EVAL_TOLERANCE})"
        ),
    )
    parser.add_argument(
        "--stat",
        choices=("min", "median", "mean", "max"),
        default="min",
        help="pytest-benchmark statistic to compare (default: min, the noise-free round)",
    )
    parser.add_argument(
        "--metric",
        action="append",
        choices=tuple(EVAL_METRIC_DIRECTION),
        help="retrieval metric the gate decides on (repeatable; default hit_rate, mrr)",
    )
    parser.add_argument("--summary", help="append the markdown summary to this file")
    parser.add_argument("--out", help="write the machine-readable A/B result here")
    parser.add_argument("--base-label", default="merge base", help="summary label")
    parser.add_argument("--head-label", default="head", help="summary label")
    parser.add_argument(
        "--host-fingerprint",
        help=(
            "fingerprint of the runner that produced both files; required to "
            "adopt a report written before environment.machine existed, and "
            "validated against it when present"
        ),
    )
    parser.add_argument(
        "--show-host-fingerprint",
        action="store_true",
        help="print this machine's fingerprint and exit (the job's identity)",
    )
    args = parser.parse_args(argv)

    if args.show_host_fingerprint:
        print(host_fingerprint())
        return PASS_EXIT
    if args.spread:
        return spread(args.spread)
    if not args.base or not args.head:
        parser.error("--base and --head are required unless --spread is given")

    try:
        base_doc = json.loads(Path(args.base).read_text())
        head_doc = json.loads(Path(args.head).read_text())
    except (OSError, ValueError) as exc:
        print(
            f"::error title=Same-job measurement invalid::cannot read a result file: {exc}"
        )
        return INVALID_EXIT

    adopted: list[str] = []
    try:
        for doc in (base_doc, head_doc):
            note = adopt_host_machine(doc, args.host_fingerprint or "")
            if note:
                adopted.append(note)
    except MeasurementInvalid as exc:
        print(f"::error title=Same-job measurement invalid::{exc}")
        return INVALID_EXIT

    print(f"base: {args.base}")
    print(f"head: {args.head}")
    if args.host_fingerprint:
        print(f"job CPU fingerprint: {args.host_fingerprint}")
    print(f"base CPU fingerprint: {fingerprint(base_doc)}")
    print(f"head CPU fingerprint: {fingerprint(head_doc)}")
    print(f"base python: {interpreter(base_doc)}")
    print(f"head python: {interpreter(head_doc)}")

    metrics = args.metric or list(EVAL_GATE_METRICS)
    try:
        result = compare(
            base_doc,
            head_doc,
            stat=args.stat,
            metrics=metrics,
            host=args.host_fingerprint,
        )
    except MeasurementInvalid as exc:
        print(f"::error title=Same-job measurement invalid::{exc}")
        if args.out:
            Path(args.out).write_text(
                json.dumps(
                    {
                        "schema": "indexed.eval.ab.v1",
                        "kind": None,
                        "verdict": "invalid",
                        "tolerance": args.tolerance,
                        "unit": None,
                        "base": _side(base_doc, args.base_label),
                        "head": _side(head_doc, args.head_label),
                        "metrics": [],
                        "cases": [],
                        "warnings": [],
                        "invalid_reasons": [str(exc)],
                    },
                    indent=2,
                )
                + "\n"
            )
        return INVALID_EXIT

    tolerance = args.tolerance
    if tolerance is None:
        tolerance = EVAL_TOLERANCE if result.shape == EVAL_SHAPE else 20.0
    result.warnings[:0] = adopted
    result.decide(tolerance)

    for warning in result.warnings:
        print(f"::warning::{warning}")
    print(table(result))

    print(verdict_line(result, tolerance))
    if result.regressions:
        title = (
            "Retrieval regression"
            if result.shape == EVAL_SHAPE
            else "Benchmark regression"
        )
        for row in result.regressions:
            moved = (
                f"{row.delta:+.4f} metric points"
                if result.unit == "points"
                else f"{row.change_pct:+.1f}%"
            )
            print(
                f"::error title={title}::{row.name} is {moved} against its own "
                f"merge base ({row.base:g} -> {row.head:g}), tolerance "
                f"{tolerance:g}."
            )
        exit_code = REGRESSION_EXIT
    else:
        exit_code = PASS_EXIT

    if args.out:
        Path(args.out).write_text(
            json.dumps(
                result_json(
                    result,
                    tolerance,
                    base_doc,
                    head_doc,
                    args.base_label,
                    args.head_label,
                ),
                indent=2,
            )
            + "\n"
        )
    if args.summary:
        path = Path(args.summary)
        with path.open("a") as handle:
            handle.write(
                summary_markdown(
                    result,
                    tolerance,
                    args.base_label,
                    args.head_label,
                    base_doc,
                    head_doc,
                )
            )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
