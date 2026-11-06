"""Tests for ``scripts/benchmark_ab.py`` — the same-job benchmark gate.

The gate's verdict must not depend on which runner the job landed on, so this
proof does not either: it feeds the comparator two synthetic pytest-benchmark
result files and asserts the verdict. A head at +25 % of its own merge base
fails, +2 % passes, and a machine mismatch is a harness bug (its own exit code),
never a regression and never a pass.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_ab.py"

FULLNAME = "tests/benchmarks/test_parsing_performance.py::test_parse_large_markdown"
BASE_MEAN_S = 0.690
CPU = "AMD EPYC 7763 64-Core Processor"


def results(mean_s: float, **overrides: dict) -> dict:
    """One synthetic pytest-benchmark file, in the shape the action writes."""
    machine = {
        "cpu": {"brand_raw": CPU, "arch": "X86_64", "count": 4},
        "system": "Linux",
        "python_version": "3.14.0",
        "node": "runnervmtest",
    }
    machine.update(overrides.pop("machine", {}))
    # The gate compares the minimum, so every file has to carry `min`; the
    # other statistics are here so a caller can pull them apart.
    stats = {"mean": mean_s, "median": mean_s, "min": mean_s}
    stats.update(overrides.pop("stats", {}))
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


def test_summary_records_sources_and_verdict(tmp_path: Path):
    """The job summary carries the measured source and the verdict it earned."""
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


SELECTED = (
    "tests/benchmarks/test_parsing_performance.py::test_parse_markdown_docs",
    FULLNAME,
    "tests/system/test_search_performance.py::test_searcher_first_search",
)
EXPECTED_ARGS = tuple(
    arg for name in SELECTED for arg in ("--expected-benchmark", name)
)


def complete_results() -> dict:
    """Build a valid three-row measurement before mutating one field."""
    doc = results(BASE_MEAN_S)
    doc["benchmarks"] = [
        dict(copy.deepcopy(doc["benchmarks"][0]), fullname=name) for name in SELECTED
    ]
    return doc


def assert_invalid(proc):
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Same-job measurement invalid" in proc.stdout
    assert "gate verdict" not in proc.stdout
    assert "Traceback" not in proc.stderr


def test_selected_set_accepts_pytest_fullnames_without_tests_prefix(tmp_path: Path):
    base, head = complete_results(), complete_results()
    for row in head["benchmarks"]:
        row["fullname"] = row["fullname"].removeprefix("tests/")
    proc = run(tmp_path, base, head, *EXPECTED_ARGS)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS (3 benchmarks" in proc.stdout


@pytest.mark.parametrize("side", ["base", "head", "both"])
def test_selected_row_omission_is_invalid(tmp_path: Path, side: str):
    base, head = complete_results(), complete_results()
    if side in ("base", "both"):
        base["benchmarks"].pop()
    if side in ("head", "both"):
        head["benchmarks"].pop()
    assert_invalid(run(tmp_path, base, head, *EXPECTED_ARGS))


@pytest.mark.parametrize("side", ["base", "head"])
@pytest.mark.parametrize(
    "value",
    [
        None,
        "missing",
        "slow",
        True,
        0,
        -1,
        float("nan"),
        float("inf"),
        -float("inf"),
        10**400,
    ],
)
def test_unusable_selected_stat_is_invalid(tmp_path: Path, side: str, value):
    base, head = complete_results(), complete_results()
    doc = base if side == "base" else head
    if value == "missing":
        del doc["benchmarks"][1]["stats"]["min"]
    else:
        doc["benchmarks"][1]["stats"]["min"] = value
    assert_invalid(run(tmp_path, base, head, *EXPECTED_ARGS))


@pytest.mark.parametrize("side", ["base", "head"])
def test_duplicate_normalized_fullname_is_invalid(tmp_path: Path, side: str):
    base, head = complete_results(), complete_results()
    doc = base if side == "base" else head
    duplicate = copy.deepcopy(doc["benchmarks"][0])
    duplicate["fullname"] = duplicate["fullname"].removeprefix("tests/")
    doc["benchmarks"].append(duplicate)
    assert_invalid(run(tmp_path, base, head, *EXPECTED_ARGS))


@pytest.mark.parametrize(
    "path,value",
    [
        (("machine_info",), None),
        (("machine_info",), []),
        (("machine_info", "cpu"), None),
        (("machine_info", "cpu", "brand_raw"), " "),
        (("machine_info", "cpu", "arch"), None),
        (("machine_info", "cpu", "count"), 0),
        (("machine_info", "cpu", "count"), True),
        (("machine_info", "system"), ""),
        (("machine_info", "python_version"), None),
    ],
)
def test_equal_missing_identities_are_invalid(tmp_path: Path, path, value):
    base, head = complete_results(), complete_results()
    for doc in (base, head):
        parent = doc
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = value
    assert_invalid(run(tmp_path, base, head, *EXPECTED_ARGS))


@pytest.mark.parametrize(
    "malformed", [None, [], 4, True, {"machine_info": [], "benchmarks": []}]
)
def test_malformed_document_is_invalid(tmp_path: Path, malformed):
    assert_invalid(run(tmp_path, malformed, complete_results(), *EXPECTED_ARGS))


@pytest.mark.parametrize(
    "path,value",
    [
        (("benchmarks",), {}),
        (("benchmarks",), []),
        (("benchmarks",), [None]),
        (("benchmarks", 0, "fullname"), None),
        (("benchmarks", 0, "fullname"), " "),
        (("benchmarks", 0, "stats"), []),
    ],
)
def test_malformed_rows_are_invalid(tmp_path: Path, path, value):
    base, head = complete_results(), complete_results()
    parent = head
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    assert_invalid(run(tmp_path, base, head, *EXPECTED_ARGS))


@pytest.mark.parametrize("tolerance", ["nan", "inf", "-inf", "-1"])
def test_invalid_tolerance_cannot_waive_regression(tmp_path: Path, tolerance: str):
    proc = run(tmp_path, results(1), results(1.5), "--tolerance=" + tolerance)
    assert_invalid(proc)


def test_zero_tolerance_is_valid(tmp_path: Path):
    proc = run(tmp_path, results(1), results(1.01), "--tolerance", "0")
    assert proc.returncode == 1, proc.stdout + proc.stderr


def test_incomplete_rows_invalid_without_expected_option(tmp_path: Path):
    base, head = complete_results(), complete_results()
    head["benchmarks"].pop()
    assert_invalid(run(tmp_path, base, head))


def noise_table(
    tmp_path: Path,
    *,
    band_ms: float,
    band_pct: float = 30.0,
    gate: bool = True,
    stat: str = "min",
    name: str = FULLNAME,
) -> Path:
    """Write a one-row noise band table in the shape the derivation emits."""
    path = tmp_path / "noise.json"
    path.write_text(
        json.dumps(
            {
                "stat": stat,
                "benchmarks": {
                    name.removeprefix("tests/"): {
                        "band_ms": band_ms,
                        "band_pct": band_pct,
                        "gate": gate,
                    }
                },
            }
        )
    )
    return path


def test_delta_inside_noise_band_is_reported_not_gated(tmp_path: Path):
    """+25 % on a row whose unchanged spread is 3.5 ms is not a verdict."""
    base, head = results(BASE_MEAN_S), results(BASE_MEAN_S * 1.25)
    table = noise_table(tmp_path, band_ms=BASE_MEAN_S * 1000 * 0.30, band_pct=30.0)

    proc = run(tmp_path, base, head, "--noise-band", str(table))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "gate verdict: PASS" in proc.stdout
    assert "inside its measured noise band" in proc.stdout
    assert "::error title=Benchmark regression::" not in proc.stdout


def test_delta_past_noise_band_still_fails(tmp_path: Path):
    """Falsifiability: the same +25 % fails when it exceeds the measured band."""
    base, head = results(BASE_MEAN_S), results(BASE_MEAN_S * 1.25)
    table = noise_table(tmp_path, band_ms=BASE_MEAN_S * 1000 * 0.10, band_pct=10.0)

    proc = run(tmp_path, base, head, "--noise-band", str(table))

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "gate verdict: FAIL" in proc.stdout
    assert "noise band" in proc.stdout


def test_row_missing_from_noise_table_keeps_relative_verdict(tmp_path: Path):
    """An unmeasured benchmark is not silently excused."""
    base, head = results(BASE_MEAN_S), results(BASE_MEAN_S * 1.25)
    table = noise_table(tmp_path, band_ms=1.0, name="tests/other.py::test_other")

    proc = run(tmp_path, base, head, "--noise-band", str(table))

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "::error title=Benchmark regression::" in proc.stdout


def test_report_only_row_never_decides(tmp_path: Path):
    """A row whose spread exceeds the cap is named, never gated — even at +100 %."""
    base, head = results(BASE_MEAN_S), results(BASE_MEAN_S * 2)
    table = noise_table(tmp_path, band_ms=1.0, band_pct=120.0, gate=False)

    proc = run(tmp_path, base, head, "--noise-band", str(table))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "too large to gate; reported only" in proc.stdout
    assert "gate verdict: PASS" in proc.stdout


def test_band_for_another_statistic_is_ignored(tmp_path: Path):
    """Bands are measured on one statistic; using them for another is invalid."""
    base, head = results(BASE_MEAN_S), results(BASE_MEAN_S * 1.25)
    table = noise_table(tmp_path, band_ms=1000.0, stat="mean")

    proc = run(tmp_path, base, head, "--noise-band", str(table))

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "bands do not apply to other statistics" in proc.stdout


@pytest.mark.parametrize(
    "entry",
    [
        {},
        {"band_ms": "3", "band_pct": 30.0, "gate": True},
        {"band_ms": 0, "band_pct": 30.0, "gate": True},
        {"band_ms": 3.0, "gate": True},
        {"band_ms": 3.0, "band_pct": 30.0},
    ],
)
def test_malformed_noise_table_is_invalid(tmp_path: Path, entry):
    table = tmp_path / "noise.json"
    table.write_text(json.dumps({"stat": "min", "benchmarks": {FULLNAME: entry}}))

    proc = run(
        tmp_path,
        results(BASE_MEAN_S),
        results(BASE_MEAN_S * 1.25),
        "--noise-band",
        str(table),
    )

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Same-job measurement invalid" in proc.stdout


def test_committed_noise_table_covers_every_selected_row():
    """CI passes this table; a missing selected row would silently re-open the lottery."""
    table = json.loads((SCRIPT.parent / "benchmark_noise.json").read_text())
    bands = table["benchmarks"]
    for node in (
        "tests/benchmarks/test_parsing_performance.py::test_parse_markdown_docs",
        "tests/benchmarks/test_parsing_performance.py::test_parse_large_markdown",
        "tests/system/test_search_performance.py::test_searcher_first_search",
    ):
        assert node.removeprefix("tests/") in bands, node
    assert table["stat"] == "min"
