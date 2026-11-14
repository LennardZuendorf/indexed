"""Tests for ``scripts/derive_benchmark_noise.py`` — the measured noise band.

The band is the only thing standing between "a delta happened" and "a
regression happened", so its arithmetic is pinned here: three repeats give
3 x the population standard deviation of the compared statistic, a spread
wider than the cap is marked report-only instead of being assigned an absurd
band, and input that cannot describe one machine is refused rather than
averaged into a plausible-looking number.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "derive_benchmark_noise.py"
CPU = "AMD EPYC 7763 64-Core Processor"
NAME = "tests/system/test_search_performance.py::test_searcher_first_search"


def results(min_s: float, *, cpu: str = CPU, python: str = "3.13.18") -> dict:
    """One synthetic pytest-benchmark file for a single benchmark."""
    return {
        "machine_info": {
            "cpu": {"brand_raw": cpu, "arch": "X86_64", "count": 4},
            "system": "Linux",
            "python_version": python,
        },
        "benchmarks": [
            {
                "fullname": NAME,
                "name": NAME.rsplit("::", 1)[-1],
                "stats": {
                    "min": min_s,
                    "median": min_s,
                    "mean": min_s,
                    # The comparator's round floor is part of the derivation: a
                    # band averaged from one-round files would hide the very
                    # variance it is supposed to measure.
                    "rounds": 3,
                },
            }
        ],
    }


def run(tmp_path: Path, *docs: dict, extra: tuple[str, ...] = ()):
    """Write each document and run the derivation exactly as a human would."""
    paths = []
    for index, doc in enumerate(docs):
        path = tmp_path / f"run-{index}.json"
        path.write_text(json.dumps(doc))
        paths.append(str(path))
    return subprocess.run(
        [sys.executable, str(SCRIPT), *paths, *extra],
        capture_output=True,
        text=True,
        check=False,
    )


def test_band_is_three_sigma_of_the_repeats(tmp_path: Path):
    """Three repeats of 9.0, 10.0 and 11.0 ms: sigma 0.816 ms, band 2.449 ms."""
    out = tmp_path / "noise.json"
    proc = run(
        tmp_path,
        results(0.009),
        results(0.010),
        results(0.011),
        extra=("--out", str(out)),
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    table = json.loads(out.read_text())
    entry = table["benchmarks"][NAME.removeprefix("tests/")]
    assert entry["median_ms"] == pytest.approx(10.0, abs=1e-6)
    assert entry["sigma_ms"] == pytest.approx(0.8165, abs=1e-3)
    assert entry["band_ms"] == pytest.approx(2.4495, abs=1e-3)
    assert entry["gate"] is True
    assert table["sample"]["measurements"] == 3
    assert table["stat"] == "min"


def test_wide_spread_becomes_report_only(tmp_path: Path):
    """A 1 ms / 10 ms / 1 ms row has no resolution: named, never gated."""
    out = tmp_path / "noise.json"
    proc = run(
        tmp_path,
        results(0.001),
        results(0.010),
        results(0.001),
        extra=("--out", str(out)),
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    entry = json.loads(out.read_text())["benchmarks"][NAME.removeprefix("tests/")]
    assert entry["gate"] is False
    assert entry["band_pct"] > 50


def test_fewer_than_three_repeats_is_refused(tmp_path: Path):
    """One measurement is not a noise estimate."""
    proc = run(tmp_path, results(0.009), results(0.010))

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "at least 3" in proc.stdout


def test_mixed_machines_are_refused(tmp_path: Path):
    """A band cannot average two machines into one number."""
    proc = run(
        tmp_path,
        results(0.009),
        results(0.010),
        results(0.011, cpu="AMD EPYC 9V45 96-Core Processor"),
    )

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "CPU" in proc.stdout


def test_mixed_interpreters_are_refused(tmp_path: Path):
    proc = run(
        tmp_path, results(0.009), results(0.010), results(0.011, python="3.12.9")
    )

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Python" in proc.stdout


def test_different_benchmark_sets_are_refused(tmp_path: Path):
    """Repeats must measure the same rows, not merely the same count."""
    other = results(0.010)
    other["benchmarks"][0]["fullname"] = "tests/other.py::test_other"
    proc = run(tmp_path, results(0.009), results(0.010), other)

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "benchmark set differs" in proc.stdout


def test_written_table_is_stable_across_runs(tmp_path: Path):
    """Re-deriving the same measurements produces the same table."""
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    docs = (results(0.009), results(0.010), results(0.011))
    assert run(tmp_path, *docs, extra=("--out", str(first))).returncode == 0
    assert run(tmp_path, *docs, extra=("--out", str(second))).returncode == 0
    assert first.read_text() == second.read_text()


def test_sources_are_recorded_one_per_file(tmp_path: Path):
    """The sample block names where each file came from, in file order."""
    out = tmp_path / "noise.json"
    sources = [
        f"https://github.com/o/r/actions/runs/{n}/artifacts/{n}" for n in (1, 2, 3)
    ]
    extra = ("--out", str(out))
    for url in sources:
        extra += ("--source", url)

    proc = run(tmp_path, results(0.009), results(0.010), results(0.011), extra=extra)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(out.read_text())["sample"]["sources"] == sources


def test_a_source_count_that_does_not_match_the_files_is_refused(tmp_path: Path):
    """One URL per file, or the provenance is a guess rather than a record."""
    proc = run(
        tmp_path,
        results(0.009),
        results(0.010),
        results(0.011),
        extra=("--source", "https://github.com/o/r/actions/runs/1"),
    )

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "one source per file" in proc.stdout
