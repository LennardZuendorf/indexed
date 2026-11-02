#!/usr/bin/env python3
"""Same-job A/B comparator for the PR benchmark gate.

Reads two pytest-benchmark result files measured back to back on one runner —
the merge base (``origin/<base ref>``) and the PR head — and turns their ratio
into the gate's only verdict. No committed baseline is read here: a cross-run
number carries the machine that produced it, so it can report drift but cannot
decide a PR (.spec/tech.md § CI Benchmarking).

Two failure modes are kept apart on purpose:

* **a regression** — the head is slower than its own merge base past tolerance.
  That is a verdict, and the gate fails.
* **an invalid measurement** — the two files disagree on CPU fingerprint or
  interpreter, so the ratio measures the harness, not the diff. That is a bug to
  fix, not a verdict to record, so it exits with its own code and message.

Usage::

    python scripts/benchmark_ab.py --base base.json --head head.json \\
        --tolerance 20 --summary "$GITHUB_STEP_SUMMARY"

Exit codes: 0 pass, 1 regression, 2 measurement invalid (or unusable input).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

PASS_EXIT = 0
REGRESSION_EXIT = 1
INVALID_EXIT = 2


class MeasurementInvalid(Exception):
    """The two result files cannot be compared; there is no verdict to give."""


@dataclass
class Row:
    """One benchmark, as measured on both sides of the A/B."""

    name: str
    base_s: float
    head_s: float

    @property
    def change_pct(self) -> float:
        # Callers only build rows for base_s > 0 (see compare()).
        return (self.head_s - self.base_s) / self.base_s * 100.0


@dataclass
class Result:
    """Everything the caller needs to print, summarise and exit on."""

    rows: list[Row] = field(default_factory=list)
    regressions: list[Row] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    stat: str = "min"


def fingerprint(doc: dict) -> str:
    """CPU fingerprint of the machine that produced a result file.

    Matches the identity the workflow prints and the action compares on:
    CPU model, architecture, core count, OS. ``?`` stands in for a missing
    field so two equally broken files still compare equal-or-not honestly.
    """
    info = doc.get("machine_info") or {}
    cpu = info.get("cpu") or {}
    parts = [
        cpu.get("brand_raw"),
        cpu.get("arch"),
        cpu.get("count"),
        info.get("system"),
    ]
    return "|".join("?" if part is None else str(part) for part in parts)


def interpreter(doc: dict) -> str:
    """Python version that produced a result file."""
    return str((doc.get("machine_info") or {}).get("python_version", "?"))


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


def compare(base_doc: dict, head_doc: dict, stat: str = "min") -> Result:
    """Pair the two measurements and keep only same-machine, same-code rows.

    Raises ``MeasurementInvalid`` when the files cannot support a verdict at
    all — mismatched machine, mismatched interpreter, or nothing in common.
    """
    was, now = fingerprint(base_doc), fingerprint(head_doc)
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

    base_rows, head_rows = samples(base_doc, stat), samples(head_doc, stat)
    result = Result(stat=stat)
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


def table(rows: list[Row], stat: str) -> str:
    """Fixed-width table: absolute numbers on both sides, then the ratio."""
    lines = [
        f"{'benchmark':<64} {'base ' + stat:>14} {'head ' + stat:>14} {'change':>9}",
        "-" * 104,
    ]
    for row in rows:
        lines.append(
            f"{row.name:<64} {row.base_s * 1000:>8.2f}ms {row.head_s * 1000:>8.2f}ms "
            f"{row.change_pct:>+8.1f}%"
        )
    return "\n".join(lines)


def summary_markdown(
    result: Result, tolerance: float, base_label: str, head_label: str
) -> str:
    """GitHub job-summary section for the A/B, fingerprints included."""
    lines = [
        "## Benchmark gate: same-job A/B",
        "",
        "Both sides measured in this job on this runner, back to back, so the "
        "machine cancels out of the ratio.",
        "",
        "| Side | Source |",
        "|---|---|",
        f"| merge base | `{base_label}` |",
        f"| head | `{head_label}` |",
        "",
        f"Comparing the {result.stat} of each benchmark.",
        "",
        "| Benchmark | Merge base | Head | Change | Verdict |",
        "|---|---|---|---|---|",
    ]
    for row in result.rows:
        verdict = "**over tolerance**" if row in result.regressions else "within"
        lines.append(
            f"| `{row.name}` | {row.base_s * 1000:.2f} ms | {row.head_s * 1000:.2f} ms "
            f"| {row.change_pct:+.1f}% | {verdict} |"
        )
    lines.append("")
    if result.regressions:
        lines.append(
            f"**Verdict: FAIL** — {len(result.regressions)} of {len(result.rows)} "
            f"benchmarks regressed past {tolerance:g}% against their own merge base."
        )
    else:
        lines.append(
            f"**Verdict: PASS** — {len(result.rows)} benchmarks within "
            f"{tolerance:g}% of their own merge base."
        )
    for warning in result.warnings:
        lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare merge-base and head benchmark results from one job."
    )
    parser.add_argument("--base", required=True, help="merge-base result JSON")
    parser.add_argument("--head", required=True, help="head result JSON")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=20.0,
        help="percent the head may be slower than the base before it is a regression",
    )
    parser.add_argument(
        "--stat",
        choices=("min", "median", "mean", "max"),
        default="min",
        help="pytest-benchmark statistic to compare (default: min, the noise-free round)",
    )
    parser.add_argument("--summary", help="append the markdown summary to this file")
    parser.add_argument("--base-label", default="merge base", help="summary label")
    parser.add_argument("--head-label", default="head", help="summary label")
    args = parser.parse_args(argv)

    try:
        base_doc = json.loads(Path(args.base).read_text())
        head_doc = json.loads(Path(args.head).read_text())
    except (OSError, ValueError) as exc:
        print(
            f"::error title=Same-job measurement invalid::cannot read a result file: {exc}"
        )
        return INVALID_EXIT

    print(f"base: {args.base}")
    print(f"head: {args.head}")
    print(f"base CPU fingerprint: {fingerprint(base_doc)}")
    print(f"head CPU fingerprint: {fingerprint(head_doc)}")
    print(f"base python: {interpreter(base_doc)}")
    print(f"head python: {interpreter(head_doc)}")

    try:
        result = compare(base_doc, head_doc, args.stat)
    except MeasurementInvalid as exc:
        print(f"::error title=Same-job measurement invalid::{exc}")
        return INVALID_EXIT

    for warning in result.warnings:
        print(f"::warning::{warning}")
    print(table(result.rows, result.stat))

    result.regressions = [row for row in result.rows if row.change_pct > args.tolerance]
    if result.regressions:
        worst = max(result.regressions, key=lambda row: row.change_pct)
        print(
            f"gate verdict: FAIL ({len(result.regressions)}/{len(result.rows)} "
            f"{result.stat} over {args.tolerance:g}% of the merge base; worst "
            f"{worst.name} {worst.change_pct:+.1f}%)"
        )
        for row in result.regressions:
            print(
                f"::error title=Benchmark regression::{row.name} {result.stat} is "
                f"{row.change_pct:+.1f}% against its own merge base "
                f"({row.base_s * 1000:.2f} ms -> {row.head_s * 1000:.2f} ms), "
                f"tolerance {args.tolerance:g}%."
            )
        exit_code = REGRESSION_EXIT
    else:
        print(
            f"gate verdict: PASS ({len(result.rows)} benchmarks within "
            f"{args.tolerance:g}% of the merge base, {result.stat})"
        )
        exit_code = PASS_EXIT

    if args.summary:
        path = Path(args.summary)
        with path.open("a") as handle:
            handle.write(
                summary_markdown(
                    result, args.tolerance, args.base_label, args.head_label
                )
            )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
