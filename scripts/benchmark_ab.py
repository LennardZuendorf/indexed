#!/usr/bin/env python3
"""Same-job A/B comparator for the PR benchmark gate.

Reads two pytest-benchmark result files measured back to back on one runner —
the captured event base and its corresponding PR merge result — and turns
their ratio into the gate's only verdict. No committed baseline is read here: a cross-run
number carries the machine that produced it, so it can report drift but cannot
decide a PR (.spec/tech.md § CI Benchmarking).

Two failure modes are kept apart on purpose:

* **a regression** — the head is slower than its captured base past tolerance.
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
import math
import sys
from collections.abc import Iterable
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
class Band:
    """How far unchanged code has been seen to move, for one benchmark."""

    name: str
    band_ms: float
    band_pct: float
    gate: bool


@dataclass
class Result:
    """Everything the caller needs to print, summarise and exit on."""

    rows: list[Row] = field(default_factory=list)
    regressions: list[Row] = field(default_factory=list)
    within_noise: list[Row] = field(default_factory=list)
    not_gateable: list[Row] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    bands: dict[str, Band] = field(default_factory=dict)
    stat: str = "min"


def object_value(value: object, label: str) -> dict:
    """Require a JSON object before reading its fields."""
    if not isinstance(value, dict):
        raise MeasurementInvalid(f"{label} must be an object.")
    return value


def text_value(value: object, label: str) -> str:
    """Missing identities cannot establish a comparable experiment."""
    if not isinstance(value, str) or not value.strip():
        raise MeasurementInvalid(f"{label} must be a nonempty string.")
    return value


def fingerprint(doc: dict) -> str:
    """Validated CPU brand, architecture, core count and system identity."""
    info = object_value(object_value(doc, "result").get("machine_info"), "machine_info")
    cpu = object_value(info.get("cpu"), "machine_info.cpu")
    brand = text_value(cpu.get("brand_raw"), "cpu.brand_raw")
    arch = text_value(cpu.get("arch"), "cpu.arch")
    count = cpu.get("count")
    if type(count) is not int or count <= 0:
        raise MeasurementInvalid("cpu.count must be a positive integer.")
    system = text_value(info.get("system"), "machine_info.system")
    return f"{brand}|{arch}|{count}|{system}"


def interpreter(doc: dict) -> str:
    """Validated Python version that produced the result file."""
    info = object_value(object_value(doc, "result").get("machine_info"), "machine_info")
    return text_value(info.get("python_version"), "machine_info.python_version")


def benchmark_name(value: object) -> str:
    """pytest-benchmark fullnames can omit the common tests/ prefix."""
    return text_value(value, "benchmark fullname").removeprefix("tests/")


def samples(doc: dict, stat: str = "min") -> dict[str, float]:
    """Require unique complete rows and finite positive selected durations."""
    benchmarks = object_value(doc, "result").get("benchmarks")
    if not isinstance(benchmarks, list) or not benchmarks:
        raise MeasurementInvalid("benchmarks must be a nonempty list.")
    out: dict[str, float] = {}
    for bench in benchmarks:
        bench = object_value(bench, "benchmark")
        name = benchmark_name(bench.get("fullname"))
        if name in out:
            raise MeasurementInvalid(f"duplicate benchmark fullname: {name}.")
        stats = object_value(bench.get("stats"), f"{name} stats")
        value = stats.get(stat)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise MeasurementInvalid(f"{name} {stat} must be a numeric duration.")
        try:
            valid = math.isfinite(value) and value > 0
        except OverflowError:
            valid = False
        if not valid:
            raise MeasurementInvalid(
                f"{name} {stat} must be a finite positive duration."
            )
        out[name] = float(value)
    return out


def compare(
    base_doc: dict,
    head_doc: dict,
    stat: str = "min",
    *,
    expected_benchmarks: Iterable[str] | None = None,
) -> Result:
    """Validate both measurements completely before computing any ratios."""
    was, now = fingerprint(base_doc), fingerprint(head_doc)
    if was != now:
        raise MeasurementInvalid(f"base CPU {was} differs from merge-result CPU {now}.")
    base_py, head_py = interpreter(base_doc), interpreter(head_doc)
    if base_py != head_py:
        raise MeasurementInvalid(
            f"base Python {base_py} differs from merge-result Python {head_py}."
        )
    base_rows, head_rows = samples(base_doc, stat), samples(head_doc, stat)
    if base_rows.keys() != head_rows.keys():
        raise MeasurementInvalid(
            "base and merge result must contain identical benchmark sets."
        )
    expected = {benchmark_name(name) for name in expected_benchmarks or ()}
    missing = expected - base_rows.keys()
    if missing:
        raise MeasurementInvalid(
            f"selected benchmarks were not measured: {', '.join(sorted(missing))}."
        )
    result = Result(stat=stat)
    for name in sorted(base_rows):
        row = Row(name, base_rows[name], head_rows[name])
        if not math.isfinite(row.change_pct):
            raise MeasurementInvalid(f"{name} ratio is not finite.")
        result.rows.append(row)
    return result


def load_noise_bands(path: Path | None) -> tuple[dict[str, Band], str | None]:
    """Read the derived per-benchmark noise bands, or nothing if not given."""
    if path is None:
        return {}, None
    try:
        doc = object_value(json.loads(path.read_text()), "noise band table")
    except (OSError, ValueError) as exc:
        raise MeasurementInvalid(f"cannot read noise band table {path}: {exc}") from exc
    stat = doc.get("stat")
    if stat is not None and not isinstance(stat, str):
        raise MeasurementInvalid("noise band table stat must be a string.")
    entries = object_value(doc.get("benchmarks"), "noise band benchmarks")
    bands: dict[str, Band] = {}
    for raw_name, value in entries.items():
        entry = object_value(value, f"noise band for {raw_name}")
        band_ms, band_pct = entry.get("band_ms"), entry.get("band_pct")
        gate = entry.get("gate")
        if not isinstance(band_ms, (int, float)) or isinstance(band_ms, bool):
            raise MeasurementInvalid(
                f"noise band for {raw_name} has no numeric band_ms."
            )
        if not math.isfinite(band_ms) or band_ms <= 0:
            raise MeasurementInvalid(f"noise band for {raw_name} must be positive.")
        if not isinstance(band_pct, (int, float)) or isinstance(band_pct, bool):
            raise MeasurementInvalid(
                f"noise band for {raw_name} has no numeric band_pct."
            )
        if not isinstance(gate, bool):
            raise MeasurementInvalid(f"noise band for {raw_name} has no boolean gate.")
        bands[benchmark_name(raw_name)] = Band(
            name=raw_name, band_ms=float(band_ms), band_pct=float(band_pct), gate=gate
        )
    return bands, stat


def classify(
    result: Result, tolerance: float, bands: dict[str, Band], table_stat: str | None
) -> None:
    """Split over-tolerance rows into regressions, noise and report-only rows.

    A row fails only when it beats the relative tolerance *and* moves further
    than unchanged code has been observed to move. A row the table marks as
    not gateable is reported and never decides the job; a row the table does
    not cover keeps the plain relative verdict, so an unmeasured benchmark
    cannot be silently excused.
    """
    if table_stat is not None and table_stat != result.stat:
        result.warnings.append(
            f"noise band table was derived for the {table_stat!r} statistic but "
            f"this comparison uses {result.stat!r}; bands do not apply to other "
            "statistics and only the relative tolerance is enforced."
        )
        bands = {}
    result.bands = bands
    for row in result.rows:
        if row.change_pct <= tolerance:
            continue
        band = bands.get(row.name)
        if band is None:
            result.regressions.append(row)
        elif not band.gate:
            result.not_gateable.append(row)
        elif (row.head_s - row.base_s) * 1000.0 >= band.band_ms:
            result.regressions.append(row)
        else:
            result.within_noise.append(row)


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


def verdicts(result: Result, tolerance: float) -> dict[str, str]:
    """Per-row verdict label, including the measured band where one applies."""
    labels = {row.name: "within" for row in result.rows}
    for row in result.within_noise:
        band = result.bands.get(row.name)
        labels[row.name] = (
            f"within noise (±{band.band_ms:.2f} ms)" if band else "within noise"
        )
    for row in result.not_gateable:
        labels[row.name] = "report only (no resolution)"
    for row in result.regressions:
        labels[row.name] = "**over tolerance**"
    return labels


def summary_markdown(
    result: Result, tolerance: float, base_label: str, head_label: str
) -> str:
    """GitHub job-summary section with measured source labels and verdict."""
    lines = [
        "## Benchmark gate: same-job A/B",
        "",
        "Both sides measured in this job on this runner, back to back, so the "
        "machine cancels out of the ratio.",
        "",
        "| Side | Source |",
        "|---|---|",
        f"| base | `{base_label}` |",
        f"| merge result | `{head_label}` |",
        "",
        f"Comparing the {result.stat} of each benchmark, with the per-benchmark "
        "noise band measured from repeat runs of unchanged code.",
        "",
        "| Benchmark | Base | Merge result | Change | Band | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    labels = verdicts(result, tolerance)
    for row in result.rows:
        band = result.bands.get(row.name)
        band_text = f"±{band.band_ms:.2f} ms" if band else "—"
        if band is not None and not band.gate:
            band_text += " (report only)"
        lines.append(
            f"| `{row.name}` | {row.base_s * 1000:.2f} ms | {row.head_s * 1000:.2f} ms "
            f"| {row.change_pct:+.1f}% | {band_text} | {labels[row.name]} |"
        )
    lines.append("")
    if result.regressions:
        lines.append(
            f"**Verdict: FAIL** — {len(result.regressions)} of {len(result.rows)} "
            f"benchmarks regressed past {tolerance:g}% and past their measured noise "
            "band against their captured base."
        )
    else:
        lines.append(
            f"**Verdict: PASS** — no benchmark regressed past {tolerance:g}% and past "
            "its measured noise band against its captured base."
        )
    if result.within_noise:
        lines.append("")
        lines.append(
            f"{len(result.within_noise)} benchmark(s) exceeded {tolerance:g}% but "
            "stayed inside the largest delta unchanged code has produced on this "
            "machine class; they are reported, not gated."
        )
    if result.not_gateable:
        lines.append("")
        lines.append(
            f"{len(result.not_gateable)} benchmark(s) are report-only: their "
            "measured spread is too large to decide anything."
        )
    for warning in result.warnings:
        lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare base and head benchmark results from one job."
    )
    parser.add_argument("--base", required=True, help="base result JSON")
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
    parser.add_argument(
        "--noise-band",
        help=(
            "per-benchmark noise band table derived by "
            "scripts/derive_benchmark_noise.py; a row over tolerance only fails "
            "when its delta also exceeds this band"
        ),
    )
    parser.add_argument("--base-label", default="base", help="summary label")
    parser.add_argument("--head-label", default="head", help="summary label")
    parser.add_argument(
        "--expected-benchmark",
        action="append",
        default=[],
        help="required pytest node ID; repeat for each selected benchmark",
    )
    args = parser.parse_args(argv)

    try:
        base_doc = json.loads(Path(args.base).read_text())
        head_doc = json.loads(Path(args.head).read_text())
    except (OSError, ValueError) as exc:
        print(
            f"::error title=Same-job measurement invalid::cannot read a result file: {exc}"
        )
        return INVALID_EXIT

    try:
        if not math.isfinite(args.tolerance) or args.tolerance < 0:
            raise MeasurementInvalid("tolerance must be finite and nonnegative.")
        result = compare(
            base_doc, head_doc, args.stat, expected_benchmarks=args.expected_benchmark
        )
        bands, table_stat = load_noise_bands(
            Path(args.noise_band) if args.noise_band else None
        )
    except MeasurementInvalid as exc:
        print(f"::error title=Same-job measurement invalid::{exc}")
        return INVALID_EXIT

    print(f"base: {args.base}")
    print(f"head: {args.head}")
    print(f"base CPU fingerprint: {fingerprint(base_doc)}")
    print(f"head CPU fingerprint: {fingerprint(head_doc)}")
    print(f"base python: {interpreter(base_doc)}")
    print(f"head python: {interpreter(head_doc)}")

    print(table(result.rows, result.stat))

    classify(result, args.tolerance, bands, table_stat)
    for row in result.within_noise:
        band = result.bands[row.name]
        print(
            f"::warning::{row.name} {result.stat} is {row.change_pct:+.1f}% "
            f"({(row.head_s - row.base_s) * 1000:.2f} ms) over the "
            f"{args.tolerance:g}% tolerance but inside its measured noise band "
            f"of ±{band.band_ms:.2f} ms ({band.band_pct:.1f}% over {band.name!r}); "
            "not a regression."
        )
    for row in result.not_gateable:
        band = result.bands[row.name]
        print(
            f"::warning::{row.name} {result.stat} is {row.change_pct:+.1f}% over the "
            f"{args.tolerance:g}% tolerance, but its measured spread "
            f"(±{band.band_ms:.2f} ms) is too large to gate; reported only."
        )
    for warning in result.warnings:
        print(f"::warning::{warning}")

    if result.regressions:
        worst = max(result.regressions, key=lambda row: row.change_pct)
        print(
            f"gate verdict: FAIL ({len(result.regressions)}/{len(result.rows)} "
            f"{result.stat} past {args.tolerance:g}% and past their measured noise "
            f"band; worst {worst.name} {worst.change_pct:+.1f}%)"
        )
        for row in result.regressions:
            band = result.bands.get(row.name)
            band_note = f", noise band ±{band.band_ms:.2f} ms" if band else ""
            print(
                f"::error title=Benchmark regression::{row.name} {result.stat} is "
                f"{row.change_pct:+.1f}% against its captured base "
                f"({row.base_s * 1000:.2f} ms -> {row.head_s * 1000:.2f} ms), "
                f"tolerance {args.tolerance:g}%{band_note}."
            )
        exit_code = REGRESSION_EXIT
    else:
        print(
            f"gate verdict: PASS ({len(result.rows)} benchmarks within "
            f"{args.tolerance:g}% or their measured noise band of the base, "
            f"{result.stat}; {len(result.within_noise)} inside noise, "
            f"{len(result.not_gateable)} report-only)"
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
