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
import platform
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_ab.py"

FULLNAME = "tests/benchmarks/test_parsing_performance.py::test_parse_large_markdown"
BASE_MEAN_S = 0.690
CPU = "AMD EPYC 7763 64-Core Processor"
#: Fixture-set identity the measuring job stamps in; one value means "same corpus".
BENCH_CORPUS = "d" * 64
WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "python-benchmark.yml"
)


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
    stats = {"mean": mean_s, "median": mean_s, "min": mean_s, "rounds": 3}
    stats.update(overrides.pop("stats", {}))
    return {
        "machine_info": machine,
        "benchmark_corpus": {"files": 3, "sha256": BENCH_CORPUS},
        "benchmarks": [
            {
                "fullname": FULLNAME,
                "name": FULLNAME.rsplit("::", 1)[-1],
                "stats": stats,
            }
        ],
    }


def run_files(base_path: Path, head_path: Path, *extra: str):
    """Run the comparator over two files exactly as CI does."""
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


def run(tmp_path: Path, base: dict, head: dict, *extra: str):
    """Write both files and run the comparator exactly as CI does."""
    base_path = tmp_path / "base.json"
    head_path = tmp_path / "head.json"
    base_path.write_text(json.dumps(base))
    head_path.write_text(json.dumps(head))
    return run_files(base_path, head_path, *extra)


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


def assert_invalid(proc, title: str = "Same-job measurement invalid"):
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert title in proc.stdout
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
    """Build complete evidence first; negative tests mutate exactly one field."""
    from indexed.eval.metrics import aggregate, score_case

    queries = []
    for number in range(104):
        relevant = ["target.md"] if number < 100 else []
        rank = (
            (1 if number < int(mrr * 100) else 2) if number < int(hit_rate * 100) else 6
        )
        ranked = (
            [f"other-{i}.md" for i in range(rank - 1)] + ["target.md"]
            if relevant
            else (["decoy.md"] if number < 100 + leak else [])
        )
        query = score_case(
            case_id=f"q{number}",
            query="question",
            ranked_doc_ids=ranked,
            relevant=relevant,
            distractors=[] if relevant else ["decoy.md"],
            k=5,
        )
        query.update(
            provenance="fixture",
            rationale="target answers question",
            elapsed_ms=1.0,
            ranking=[
                dict(rank=i, doc=doc, chunk=0, score=0.9, score_kind="cosine")
                for i, doc in enumerate(ranked, 1)
            ],
        )
        queries.append(query)
    return dict(
        schema="indexed.eval.report.v1",
        generated_at="2026-11-02T10:00:00+00:00",
        corpus=dict(tree_sha256=CORPUS, source_repo_rev="rev", files=[]),
        case_set=dict(sha256=case_set, path="cases.json", cases=len(queries)),
        config=dict(
            collection="eval-corpus",
            engine="2",
            top_k=5,
            max_docs=10,
            rerank=False,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            score_kind="cosine",
        ),
        metrics=aggregate(queries, 5),
        queries=queries,
        failures=[],
        environment=dict(
            python="3.13.18",
            platform="Linux-6.11.0-1018-azure-x86_64-with-glibc2.39",
            indexed_version="test",
            embedding_model_cache=dict(
                cache_dir="/cache",
                present=True,
                weights=["model.safetensors"],
                selected_snapshot="same",
            ),
            machine=dict(
                cpu=dict(brand_raw=cpu, arch="x86_64", count=4), system="Linux"
            ),
            indexed_git_rev=revision,
        ),
    )


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
    assert "mrr      spread 0.000000" in proc.stdout
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


@pytest.mark.parametrize(
    "path,value",
    [
        (("queries",), []),
        (("queries",), {}),
        (("metrics", "hit_rate"), None),
        (("metrics", "mrr"), float("nan")),
        (("config", "embedding_model"), "different"),
        (("config", "score_kind"), "distance"),
        (("environment",), []),
        (("environment", "machine", "cpu"), []),
        (("queries", 0, "relevant"), ["different.md"]),
        (("queries", 0, "query"), "another question"),
        (("queries", 0, "id"), "changed-id"),
        (("queries", 0, "ranking", 0, "score"), float("nan")),
        (("metrics", "mrr"), 10**400),
        (("queries", 0, "ranking", 0, "score"), 10**400),
    ],
)
def test_eval_invalid_evidence_has_safe_invalid_json(tmp_path, path, value):
    base, head = eval_report(0.82, 0.69), eval_report(0.82, 0.69)
    parent = head
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    out = tmp_path / "invalid.json"
    proc = run(tmp_path, base, head, "--out", str(out))
    assert_invalid(proc)
    assert json.loads(out.read_text())["verdict"] == "invalid"


@pytest.mark.parametrize(
    "value", [[], None, 7, {"schema": "indexed.eval.report.v1", "environment": []}]
)
def test_eval_bad_container_writes_invalid_json(tmp_path, value):
    out = tmp_path / "invalid.json"
    assert_invalid(run(tmp_path, value, eval_report(0.82, 0.69), "--out", str(out)))
    assert json.loads(out.read_text())["verdict"] == "invalid"


def test_eval_selected_metric_is_mandatory(tmp_path):
    base, head = eval_report(0.82, 0.69), eval_report(0.82, 0.69)
    for report in (base, head):
        del report["metrics"]["hit_rate"]
    assert_invalid(run(tmp_path, base, head))


def test_eval_mrr_regression_with_stable_hit_rate_fails(tmp_path):
    proc = run(tmp_path, eval_report(0.82, 0.69), eval_report(0.82, 0.59))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "mrr is -0.0500 metric points" in proc.stdout


def test_eval_changed_model_snapshot_is_invalid(tmp_path):
    base, head = eval_report(0.82, 0.69), eval_report(0.82, 0.69)
    head["environment"]["embedding_model_cache"]["selected_snapshot"] = "other"
    assert_invalid(run(tmp_path, base, head))


def test_eval_json_integer_limit_writes_invalid_result(tmp_path):
    base, head, out = (
        tmp_path / "base.json",
        tmp_path / "head.json",
        tmp_path / "invalid.json",
    )
    base.write_text('{"schema":"indexed.eval.report.v1","value":' + "9" * 5000 + "}")
    head.write_text(json.dumps(eval_report(0.82, 0.69)))
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--base",
            str(base),
            "--head",
            str(head),
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert_invalid(proc)
    assert json.loads(out.read_text())["verdict"] == "invalid"


_MISSING = object()


def instrumented_report():
    report = eval_report(0.82, 0.69)
    report["config"]["input_context_policy"] = "eval-corpus-relative-v1"
    report["environment"]["common_harness"] = {
        "revision": "a" * 40,
        "policy": "eval-corpus-relative-v1",
        "files_sha256": {"launcher": "b" * 64, "canonical_helper": "c" * 64},
    }
    return report


@pytest.mark.parametrize("side", ["base", "head", "both"])
@pytest.mark.parametrize("value", [[], None, 7, "bad"])
def test_malformed_reranker_cache_emits_invalid_json(tmp_path, side, value):
    base, head = instrumented_report(), instrumented_report()
    for label, report in (("base", base), ("head", head)):
        if side in (label, "both"):
            report["environment"]["reranker_model_cache"] = value
    out = tmp_path / "invalid.json"
    assert_invalid(run(tmp_path, base, head, "--out", str(out)))
    assert json.loads(out.read_text())["verdict"] == "invalid"


@pytest.mark.parametrize("side", ["head", "both"])
@pytest.mark.parametrize(
    "path,value",
    [
        (("embedding_model_cache", "selected_snapshot"), _MISSING),
        (("embedding_model_cache", "selected_snapshot"), []),
        (("embedding_model_cache", "selected_snapshot"), " "),
        (("embedding_model_cache", "weights"), []),
        (("common_harness", "revision"), _MISSING),
        (("common_harness", "revision"), "bad"),
        (("common_harness", "policy"), _MISSING),
        (("common_harness", "policy"), []),
        (("common_harness", "policy"), "other-policy"),
        (("common_harness", "files_sha256"), _MISSING),
        (("common_harness", "files_sha256"), []),
        (("common_harness", "files_sha256", "launcher"), _MISSING),
        (("common_harness", "files_sha256", "launcher"), "not-a-hash"),
        (("common_harness", "files_sha256", "canonical_helper"), "g" * 64),
    ],
)
def test_incomplete_gate_identity_emits_invalid_json(tmp_path, side, path, value):
    base, head = instrumented_report(), instrumented_report()
    for label, report in (("base", base), ("head", head)):
        if side not in (label, "both"):
            continue
        parent = report["environment"]
        for key in path[:-1]:
            parent = parent[key]
        if value is _MISSING:
            del parent[path[-1]]
        else:
            parent[path[-1]] = value
    out = tmp_path / "invalid.json"
    assert_invalid(run(tmp_path, base, head, "--out", str(out)))
    assert json.loads(out.read_text())["verdict"] == "invalid"


@pytest.mark.parametrize("active", [False, True])
def test_reranker_absence_is_compatible_only_when_inactive(tmp_path, active):
    base, head = instrumented_report(), instrumented_report()
    for report in (base, head):
        report["config"]["rerank"] = active
    out = tmp_path / "result.json"
    proc = run(tmp_path, base, head, "--out", str(out))
    if active:
        assert_invalid(proc)
        assert json.loads(out.read_text())["verdict"] == "invalid"
    else:
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_canonical_ci_requires_common_harness_but_local_remains_compatible(tmp_path):
    base, head = eval_report(0.82, 0.69), eval_report(0.82, 0.69)
    assert run(tmp_path, base, head).returncode == 0
    out = tmp_path / "invalid.json"
    assert_invalid(
        run(tmp_path, base, head, "--require-common-harness", "--out", str(out))
    )
    assert json.loads(out.read_text())["verdict"] == "invalid"
    assert (
        run(
            tmp_path,
            instrumented_report(),
            instrumented_report(),
            "--require-common-harness",
        ).returncode
        == 0
    )


def test_host_fingerprint_falls_back_after_readable_cpuinfo_without_model(monkeypatch):
    import runpy

    namespace = runpy.run_path(str(SCRIPT))
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *args, **kwargs: "processor: 0\nCPU implementer: 0x41\n",
    )
    monkeypatch.setattr(namespace["platform"], "processor", lambda: "arm processor")
    assert namespace["host_fingerprint"]().startswith("arm processor|")


@pytest.mark.parametrize("both", [False, True])
def test_errored_query_cannot_disappear_from_gate_denominators(tmp_path, both):
    from indexed.eval.metrics import aggregate, score_case

    base, head = instrumented_report(), instrumented_report()
    for report in (base, head) if both else (head,):
        record = report["queries"][0]
        record.update(
            score_case(
                case_id=record["id"],
                query=record["query"],
                ranked_doc_ids=[],
                relevant=record["relevant"],
                distractors=record["distractors"],
                k=5,
                error="retrieval failed",
            )
        )
        record["ranking"] = []
        report["metrics"] = aggregate(report["queries"], 5)
        report["failures"] = [{"id": record["id"], "error": record["error"]}]
    out = tmp_path / "invalid.json"
    assert_invalid(run(tmp_path, base, head, "--out", str(out)))
    assert json.loads(out.read_text())["verdict"] == "invalid"


@pytest.mark.parametrize("failure", ["read", "adoption"])
def test_early_failure_always_writes_invalid_artifact(tmp_path, failure):
    out = tmp_path / "invalid.json"
    if failure == "adoption":
        base = legacy_report(0.82, 0.69, machine_platform="wrong platform")
        proc = run(
            tmp_path,
            base,
            eval_report(0.82, 0.69),
            "--host-fingerprint",
            host_fingerprint(),
            "--out",
            str(out),
        )
    else:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--base",
                str(tmp_path / "absent.json"),
                "--head",
                str(tmp_path / "absent-head.json"),
                "--out",
                str(out),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    assert_invalid(proc)
    assert json.loads(out.read_text())["verdict"] == "invalid"


@pytest.mark.parametrize("path", [("corpus", "tree_sha256"), ("case_set", "sha256")])
def test_equal_missing_experiment_hashes_are_invalid(tmp_path, path):
    base, head = instrumented_report(), instrumented_report()
    for report in (base, head):
        del report[path[0]][path[1]]
    out = tmp_path / "invalid.json"
    assert_invalid(run(tmp_path, base, head, "--out", str(out)))
    assert json.loads(out.read_text())["verdict"] == "invalid"


def test_active_reranker_requires_model_identity_and_accepts_complete_cache(tmp_path):
    from copy import deepcopy

    base, head = instrumented_report(), instrumented_report()
    for report in (base, head):
        report["config"]["rerank"] = True
        report["environment"]["reranker_model_cache"] = deepcopy(
            report["environment"]["embedding_model_cache"]
        )
    out = tmp_path / "invalid.json"
    assert_invalid(run(tmp_path, base, head, "--out", str(out)))
    assert json.loads(out.read_text())["verdict"] == "invalid"
    for report in (base, head):
        report["config"]["reranker_model"] = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert run(tmp_path, base, head).returncode == 0


# --- the benchmark lane must prove it measured something -------------------
#
# Both guards below were absent until the #297 review: two files with
# ``rounds: 1`` earned a PASS, and two runs over different corpora were
# compared as like-for-like. A gate that goes green having measured nothing is
# the defect this repository spent two weeks fixing, so each refusal is
# asserted by name and the workflow that calls it is pinned.


@pytest.mark.parametrize("value", [1, 2, 0, True, "3", None])
def test_fewer_than_three_rounds_is_refused(tmp_path: Path, value):
    """One round is the runner's mood, not the diff: it cannot earn a verdict."""
    base, head = complete_results(), complete_results()
    for doc in (base, head):
        for row in doc["benchmarks"]:
            row["stats"]["rounds"] = value
    assert_invalid(run(tmp_path, base, head, *EXPECTED_ARGS))


def test_rounds_refusal_names_the_round_count(tmp_path: Path):
    """The message has to say how many repeats it got, or it cannot be actioned."""
    base, head = complete_results(), complete_results()
    for doc in (base, head):
        doc["benchmarks"][1]["stats"]["rounds"] = 1
    proc = run(tmp_path, base, head, *EXPECTED_ARGS)
    assert_invalid(proc)
    assert "reports 1 round for" in proc.stdout
    assert "needs at least 3 repeats" in proc.stdout


def test_three_rounds_still_earns_a_verdict(tmp_path: Path):
    """The guard refuses unproven runs, not proven ones."""
    proc = run(tmp_path, complete_results(), complete_results())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "gate verdict: PASS" in proc.stdout


def fixture_corpus(root: Path, files: dict[str, str]) -> Path:
    """A stand-in for tests/benchmarks/fixtures, nested file included."""
    root.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root


def stamp(path: Path, corpus: Path):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--stamp-corpus",
            str(path),
            "--corpus-root",
            str(corpus),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_stamped_results_over_one_corpus_pass(tmp_path: Path):
    """The writer round trip: both sides digest the same tree, so the gate decides."""
    corpus = fixture_corpus(
        tmp_path / "corpus", {"a.md": "alpha", "features/b.md": "beta"}
    )
    base, head = results(BASE_MEAN_S), results(BASE_MEAN_S * 1.02)
    for doc in (base, head):
        del doc["benchmark_corpus"]
    base_path, head_path = tmp_path / "base.json", tmp_path / "head.json"
    for path, doc in ((base_path, base), (head_path, head)):
        path.write_text(json.dumps(doc))
        stamped = stamp(path, corpus)
        assert stamped.returncode == 0, stamped.stdout + stamped.stderr
        assert json.loads(path.read_text())["benchmark_corpus"]["files"] == 2
    proc = run_files(base_path, head_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "gate verdict: PASS" in proc.stdout
    assert "base corpus: " in proc.stdout and "head corpus: " in proc.stdout


def test_benchmarks_over_different_corpora_are_refused(tmp_path: Path):
    """A corpus change is a different experiment, never a regression or a pass."""
    was = fixture_corpus(tmp_path / "was", {"a.md": "alpha"})
    now = fixture_corpus(tmp_path / "now", {"a.md": "alpha, but changed"})
    base_path, head_path = tmp_path / "base.json", tmp_path / "head.json"
    for path, corpus in ((base_path, was), (head_path, now)):
        path.write_text(json.dumps(results(BASE_MEAN_S)))
        assert stamp(path, corpus).returncode == 0
    proc = run_files(base_path, head_path)
    assert_invalid(proc)
    assert "corpus change is a different experiment" in proc.stdout


def test_benchmark_result_without_corpus_identity_is_refused(tmp_path: Path):
    """Missing identity is a refusal: an unnamed corpus cannot be compared."""
    base, head = complete_results(), complete_results()
    for doc in (base, head):
        del doc["benchmark_corpus"]
    proc = run(tmp_path, base, head, *EXPECTED_ARGS)
    assert_invalid(proc)
    assert "carries no benchmark_corpus identity" in proc.stdout


@pytest.mark.parametrize("case", ["empty-corpus", "eval-file", "absent-file"])
def test_stamp_refuses_what_it_cannot_identify(tmp_path: Path, case: str):
    """The writer fails closed too: no corpus or no benchmark rows is exit 2."""
    corpus = fixture_corpus(tmp_path / "corpus", {"a.md": "alpha"})
    path = tmp_path / "result.json"
    path.write_text(json.dumps(results(BASE_MEAN_S)))
    if case == "empty-corpus":
        corpus = tmp_path / "empty"
        corpus.mkdir()
    elif case == "eval-file":
        path.write_text(json.dumps({"schema": "indexed.eval.report.v1"}))
    else:
        path.unlink()
    assert_invalid(stamp(path, corpus), "Benchmark corpus identity invalid")


def step_block(name: str) -> str:
    """The YAML block of one workflow step, found by its ``- name:`` line."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() != f"- name: {name}":
            continue
        indent = len(line) - len(line.lstrip())
        block = [line]
        for following in lines[index + 1 :]:
            stripped = len(following) - len(following.lstrip())
            if following.lstrip().startswith("- name:") and stripped <= indent:
                break
            block.append(following)
        return "\n".join(block)
    raise AssertionError(f"python-benchmark.yml has no step named {name!r}")


def trap_handler(block: str) -> tuple[str, str]:
    """The ERR trap's own handler and signal, parsed from one step's run block."""
    traps = [
        line.strip() for line in block.splitlines() if line.strip().startswith("trap ")
    ]
    assert len(traps) == 1, (
        f"expected one trap statement in the gate, found {len(traps)}"
    )
    match = re.fullmatch(r"trap '(.+)' (\w+)", traps[0])
    assert match is not None, f"unrecognised trap statement: {traps[0]!r}"
    return match.group(1), match.group(2)


def test_ab_gate_step_is_pinned_with_its_failure_path():
    """Deleting the gate must red a check, not silently stop gating."""
    block = step_block("Same-job A/B gate (captured base vs merge result)")
    handler, signal = trap_handler(block)
    assert signal == "ERR"
    assert "::error title=Same-job measurement invalid::" in handler
    assert handler.rstrip().endswith("; exit 2"), handler
    assert 'AB_TOLERANCE: "20"' in block
    assert 'exit "$status"' in block
    # Both measured sides are stamped with their own fixture-set identity.
    assert "--stamp-corpus" in block
    assert 'measure "$BASE_DIR" "$BASE_SHA"' in block
    assert 'measure "$MERGE_DIR" "$MERGE_SHA"' in block


def test_report_step_keeps_its_advisory_tolerance():
    """The A/B verdict rests on this being report policy, not a safety boundary."""
    block = step_block("Run benchmarks")
    assert "continue-on-error: true" in block
    assert "cross-branch-tolerance: 1000" in block
