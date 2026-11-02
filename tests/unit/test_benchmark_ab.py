"""Tests for ``scripts/benchmark_ab.py`` — the same-job benchmark gate.

The gate's verdict must not depend on which runner the job landed on, so this
proof does not either: it feeds the comparator two synthetic pytest-benchmark
result files and asserts the verdict. A head at +25 % of its own merge base
fails, +2 % passes, and a machine mismatch is a harness bug (its own exit code),
never a regression and never a pass.
"""

from __future__ import annotations

import json
import platform
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
    # The gate compares the minimum, so every file has to carry `min`; the
    # other statistics are here so a caller can pull them apart.
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


# --- retrieval gate: two ``indexed.eval.report.v1`` files, same job --------
#
# The gate on the product's actual promise must not depend on the runner either,
# so these feed the same comparator two synthetic retrieval reports. The
# tolerance is in metric points (``EVAL_TOLERANCE``), not percent.

EVAL_CPU = "AMD EPYC 7763 64-Core Processor"
CORPUS = "a" * 64
CASES = "b" * 64


def eval_report(
    hit_rate: float,
    mrr: float,
    *,
    leak: int = 2,
    cpu: str = EVAL_CPU,
    case_set: str = CASES,
    revision: str = "abc1234",
) -> dict:
    """One synthetic retrieval report, in the shape ``indexed-eval run`` writes."""
    return {
        "schema": "indexed.eval.report.v1",
        "generated_at": "2026-11-02T10:00:00+00:00",
        "corpus": {"tree_sha256": CORPUS},
        "case_set": {"sha256": case_set},
        "config": {
            "collection": "eval-corpus",
            "engine": "2",
            "top_k": 5,
            "max_docs": 10,
            "rerank": False,
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "score_kind": "cosine",
        },
        "metrics": {
            "k": 5,
            "cases": 2,
            "answerable": 2,
            "unanswerable": 1,
            "errors": 0,
            "hit_rate": hit_rate,
            "mrr": mrr,
            "unanswerable_distractor_leaks": leak,
        },
        "queries": [
            {"id": "q1", "first_relevant_rank": 1},
            {"id": "q2", "first_relevant_rank": 2},
        ],
        "environment": {
            "python": "3.13.18",
            "platform": "Linux-6.11.0-1018-azure-x86_64-with-glibc2.39",
            "machine": {
                "cpu": {"brand_raw": cpu, "arch": "x86_64", "count": 4},
                "system": "Linux",
            },
            "indexed_git_rev": revision,
        },
    }


def test_eval_head_five_points_down_fails(tmp_path: Path):
    """The red proof: a hit-rate drop past the measured tolerance is a failing verdict."""
    proc = run(
        tmp_path,
        eval_report(0.82, 0.69),
        eval_report(0.77, 0.65),
    )

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "gate verdict: FAIL" in proc.stdout
    assert "::error title=Retrieval regression::" in proc.stdout
    assert "hit_rate is -0.0500 metric points" in proc.stdout


def test_eval_head_one_point_down_passes(tmp_path: Path):
    """A move inside the measured spread is not a regression."""
    proc = run(tmp_path, eval_report(0.82, 0.69), eval_report(0.81, 0.68))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "gate verdict: PASS" in proc.stdout


def test_eval_leak_count_is_reported_not_gated(tmp_path: Path):
    """Leaks are informative by ruling (#204): the gate decides on hit-rate and MRR."""
    proc = run(tmp_path, eval_report(0.82, 0.69), eval_report(0.82, 0.69, leak=4))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "gate verdict: PASS" in proc.stdout
    assert "report only" in proc.stdout


def test_eval_both_fingerprints_are_printed(tmp_path: Path):
    """The evidence line: identical machine fingerprints, one per side."""
    proc = run(tmp_path, eval_report(0.82, 0.69), eval_report(0.82, 0.69))

    assert f"base CPU fingerprint: {EVAL_CPU}|x86_64|4|Linux" in proc.stdout
    assert f"head CPU fingerprint: {EVAL_CPU}|x86_64|4|Linux" in proc.stdout


def test_eval_different_machine_is_an_invalid_measurement(tmp_path: Path):
    """A machine mismatch is a harness bug with no verdict — not a red PR."""
    proc = run(
        tmp_path,
        eval_report(0.82, 0.69),
        eval_report(0.82, 0.69, cpu="AMD EPYC 9V74 96-Core Processor"),
    )

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "Same-job measurement invalid" in proc.stdout
    assert "gate verdict" not in proc.stdout


def test_eval_different_case_set_is_an_invalid_measurement(tmp_path: Path):
    """Two different experiments are not a verdict on this diff."""
    proc = run(
        tmp_path,
        eval_report(0.82, 0.69),
        eval_report(0.95, 0.9, case_set="c" * 64),
    )

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "the pinned case set differs" in proc.stdout


def test_eval_out_json_carries_verdict_and_revisions(tmp_path: Path):
    """The PR comment reads its verdict and both revisions from this file."""
    out = tmp_path / "eval-ab.json"
    proc = run(
        tmp_path,
        eval_report(0.82, 0.69, revision="base123"),
        eval_report(0.77, 0.65, revision="head456"),
        "--out",
        str(out),
        "--base-label",
        "origin/main @ base123",
    )

    assert proc.returncode == 1, proc.stdout + proc.stderr
    document = json.loads(out.read_text())
    assert document["schema"] == "indexed.eval.ab.v1"
    assert document["verdict"] == "fail"
    assert document["base"]["revision"] == "base123"
    assert document["head"]["revision"] == "head456"
    assert document["base"]["fingerprint"] == document["head"]["fingerprint"]
    assert {row["name"] for row in document["metrics"]} == {
        "hit_rate",
        "mrr",
        "unanswerable_distractor_leaks",
    }
    assert document["invalid_reasons"] == []


def test_spread_reports_run_to_run_variance(tmp_path: Path):
    """The tolerance's provenance: repeats of one tree, measured in one job."""
    paths = []
    for index in range(3):
        path = tmp_path / f"run{index}.json"
        path.write_text(json.dumps(eval_report(0.82, 0.69)))
        paths.append(str(path))

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--spread", *paths],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "hit_rate spread 0.000000 (0.8200..0.8200 over 3 runs)" in proc.stdout
    assert "mrr      spread 0.000000 (0.6900..0.6900 over 3 runs)" in proc.stdout
    assert "cases with a rank difference across repeats: 0" in proc.stdout


# --- the bootstrap A/B: a merge base that predates environment.machine -----
#
# The PR that introduces the machine block is measured against a base written by
# code without it. The job knows its own machine, so it stamps that fingerprint
# into the legacy report — but only after the report's own platform string
# proves it was produced here. A report from another machine stays invalid.


def host_fingerprint() -> str:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--show-host-fingerprint"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip()


def legacy_report(hit_rate: float, mrr: float, *, machine_platform: str) -> dict:
    """A pre-machine-block retrieval report: platform string, no machine block."""
    doc = eval_report(hit_rate, mrr)
    doc["environment"].pop("machine")
    doc["environment"]["platform"] = machine_platform
    return doc


def test_eval_legacy_base_adopts_the_job_fingerprint(tmp_path: Path):
    """The bootstrap PR gates: the job names the host both sides ran on."""
    host = host_fingerprint()
    proc = run(
        tmp_path,
        legacy_report(0.82, 0.69, machine_platform=platform.platform()),
        legacy_report(0.81, 0.68, machine_platform=platform.platform()),
        "--host-fingerprint",
        host,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"job CPU fingerprint: {host}" in proc.stdout
    assert f"base CPU fingerprint: {host}" in proc.stdout
    assert f"head CPU fingerprint: {host}" in proc.stdout
    assert "adopted this job's fingerprint" in proc.stdout
    assert "gate verdict: PASS" in proc.stdout


def test_eval_legacy_report_from_another_machine_is_invalid(tmp_path: Path):
    """Adoption checks provenance: another host's platform string is refused."""
    proc = run(
        tmp_path,
        legacy_report(
            0.82, 0.69, machine_platform="Linux-6.11.0-1018-azure-x86_64-with-glibc2.39"
        ),
        legacy_report(0.82, 0.69, machine_platform=platform.platform()),
        "--host-fingerprint",
        host_fingerprint(),
    )

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "was not produced on this machine" in proc.stdout
    assert "gate verdict" not in proc.stdout


def test_eval_report_on_another_cpu_than_the_job_is_invalid(tmp_path: Path):
    """A recorded machine that disagrees with the runner is a harness bug."""
    proc = run(
        tmp_path,
        eval_report(0.82, 0.69),
        eval_report(0.82, 0.69),
        "--host-fingerprint",
        "Some Other CPU|x86_64|2|Linux",
    )

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "but this job runs on" in proc.stdout
    assert "gate verdict" not in proc.stdout
