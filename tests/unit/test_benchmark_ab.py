"""Tests for ``scripts/benchmark_ab.py`` — the same-job benchmark gate.

The gate's verdict must not depend on which runner the job landed on, so this
proof does not either: it feeds the comparator two synthetic pytest-benchmark
result files and asserts the verdict. A head at +25 % of its own merge base
fails, +2 % passes, and a machine mismatch is a harness bug (its own exit code),
never a regression and never a pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_ab.py"

FULLNAME = "tests/benchmarks/test_parsing_performance.py::test_parse_large_markdown"
BASE_MEAN_S = 0.690
CPU = "AMD EPYC 7763 64-Core Processor"


def results(mean_s: float, **overrides: object) -> dict:
    """One synthetic pytest-benchmark file, in the shape the action writes."""
    machine = {
        "cpu": {"brand_raw": CPU, "arch": "X86_64", "count": 4},
        "system": "Linux",
        "python_version": "3.14.0",
        "node": "runnervmtest",
    }
    machine.update(overrides.pop("machine", {}))  # type: ignore[arg-type]
    # median and mean agree unless a caller sets them apart: the gate compares
    # the median, so a file has to carry it.
    stats = {"mean": mean_s, "median": mean_s, "min": mean_s}
    stats.update(overrides.pop("stats", {}))  # type: ignore[arg-type]
    return {
        "machine_info": machine,
        "benchmarks": [
            {
                "fullname": FULLNAME,
                "name": FULLNAME.rsplit("::", 1)[-1],
                "stats": stats,
            }
        ],
    }


def run(tmp_path: Path, base: dict, head: dict, *extra: str):
    """Write both files and run the comparator exactly as CI does."""
    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--base",
            str(base_path),
            "--head",
            str(head_path),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_head_twenty_five_percent_slower_fails(tmp_path: Path):
    """The red proof: a real regression past tolerance is a failing verdict."""
    proc = run(tmp_path, results(BASE_MEAN_S), results(BASE_MEAN_S * 1.25))

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "gate verdict: FAIL" in proc.stdout
    assert "::error title=Benchmark regression::" in proc.stdout
    assert "+25.0%" in proc.stdout


def test_head_two_percent_slower_passes(tmp_path: Path):
    """Noise-sized drift passes: the tolerance is not a hair trigger."""
    proc = run(tmp_path, results(BASE_MEAN_S), results(BASE_MEAN_S * 1.02))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "gate verdict: PASS" in proc.stdout


def test_one_slow_round_does_not_red_the_gate(tmp_path: Path):
    """One slow round is not a regression: the gate compares the best round."""
    # Same tree both sides, one noisy round on the head drags its mean 30 % and
    # its median 2 % while its fastest round is unchanged. Comparing means would
    # red this — that lottery is exactly what this gate replaces.
    head = results(
        BASE_MEAN_S,
        stats={
            "min": BASE_MEAN_S,
            "median": BASE_MEAN_S * 1.02,
            "mean": BASE_MEAN_S * 1.30,
        },
    )
    proc = run(tmp_path, results(BASE_MEAN_S), head)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "gate verdict: PASS" in proc.stdout


def test_both_fingerprints_are_printed(tmp_path: Path):
    """The evidence line: identical fingerprints, one per side."""
    proc = run(tmp_path, results(BASE_MEAN_S), results(BASE_MEAN_S * 1.02))

    assert f"base CPU fingerprint: {CPU}|X86_64|4|Linux" in proc.stdout
    assert f"head CPU fingerprint: {CPU}|X86_64|4|Linux" in proc.stdout


def test_different_cpu_is_an_invalid_measurement(tmp_path: Path):
    """A machine mismatch is a harness bug with no verdict — not a red PR."""
    other = {
        "cpu": {
            "brand_raw": "AMD EPYC 9V45 96-Core Processor",
            "arch": "X86_64",
            "count": 4,
        }
    }
    proc = run(tmp_path, results(BASE_MEAN_S), results(BASE_MEAN_S, machine=other))

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Same-job measurement invalid" in proc.stdout
    assert "gate verdict" not in proc.stdout


def test_no_shared_rows_is_an_invalid_measurement(tmp_path: Path):
    """Comparing nothing is not a pass — the defect this gate replaced."""
    head = results(BASE_MEAN_S)
    head["benchmarks"][0]["fullname"] = "tests/system/test_other.py::test_other"

    proc = run(tmp_path, results(BASE_MEAN_S), head)

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Same-job measurement invalid" in proc.stdout


def test_summary_records_fingerprints_and_verdict(tmp_path: Path):
    """The job summary carries both fingerprints and the verdict it earned."""
    summary = tmp_path / "summary.md"
    proc = run(
        tmp_path,
        results(BASE_MEAN_S),
        results(BASE_MEAN_S * 1.25),
        "--summary",
        str(summary),
        "--base-label",
        "origin/main @ abc1234",
    )

    assert proc.returncode == 1, proc.stdout + proc.stderr
    text = summary.read_text()
    assert "origin/main @ abc1234" in text
    assert "Verdict: FAIL" in text
    assert "over tolerance" in text
