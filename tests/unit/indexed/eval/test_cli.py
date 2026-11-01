"""``indexed-eval`` CLI surfaces (issue #204).

The harness is only trustworthy if the command that commits a baseline and the
command that judges one behave as documented, so these tests drive the Typer app
with a canned report instead of a real model: the wiring, the refusals and the
exit codes are the subject here, not the ranking.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict

import pytest
from typer.testing import CliRunner

import indexed.eval.cli as cli
from indexed.eval.compare import VERDICT_INCOMPARABLE, VERDICT_REGRESSED

pytestmark = pytest.mark.unit

runner = CliRunner()


def _report(*, rank: int = 1, errors: int = 0, corpus: str = "tree-a"):
    """Build ranking evidence and metrics together for CLI comparison scenarios."""
    reciprocal_rank = round(1.0 / rank, 6)
    hit_at_k = 1.0 if rank <= 5 else 0.0
    ranked = [f"other-{n}.md" for n in range(1, rank)] + ["plan.md"]
    query = {
        "id": "case-1",
        "query": "how does search work",
        "provenance": "issue #1",
        "rationale": "the doc answers it",
        "relevant": ["plan.md"],
        "distractors": [],
        "ranked_docs": ranked,
        "k": 5,
        "elapsed_ms": 1.0,
        "ranking": [
            {"rank": n, "doc": doc, "chunk": 0, "score": 0.9, "score_kind": "cosine"}
            for n, doc in enumerate(ranked, 1)
        ],
        "first_relevant_rank": rank,
        "reciprocal_rank": reciprocal_rank,
        "hit_at_k": hit_at_k,
        "distractor_leak": None,
        "status": "scored",
        "error": None,
    }
    report: Dict[str, Any] = {
        "schema": "indexed.eval.report.v1",
        "generated_at": "2026-10-29T00:00:00+00:00",
        "case_set": {"path": "eval/cases.json", "sha256": "a" * 64, "cases": 1},
        "corpus": {
            "corpus_id": "docs",
            "tree_sha256": sha256(corpus.encode()).hexdigest(),
            "source_repo_rev": "rev",
            "files": [],
        },
        "config": {
            "engine": "2",
            "embedding_model": "m",
            "score_kind": "cosine",
            "rerank": False,
            "top_k": 5,
            "max_docs": 10,
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
        "metrics": {
            "k": 5,
            "cases": 1,
            "answerable": 1,
            "unanswerable": 0,
            "errors": errors,
            "hit_rate": None if errors else hit_at_k,
            "hit_rate_at_5": None if errors else hit_at_k,
            "mrr": None if errors else reciprocal_rank,
            "unanswerable_distractor_leaks": 0,
            "failed_by_id": ["case-1"] if errors else [],
        },
        "queries": [query],
        "failures": [],
    }
    return report


class _Canned:
    """A report the CLI can measure without a model."""

    def __init__(self) -> None:
        self.report: Dict[str, Any] = _report()


@pytest.fixture()
def canned(monkeypatch: pytest.MonkeyPatch) -> _Canned:
    """Replace the measurement, not the wiring."""

    box = _Canned()
    monkeypatch.setattr(cli, "run_eval", lambda **_kwargs: box.report)
    return box


def test_run_writes_the_report_it_measured(canned, tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    result = runner.invoke(cli.app, ["run", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text(encoding="utf-8"))["schema"] == (
        "indexed.eval.report.v1"
    )
    assert "hit@5" in result.output


def test_run_json_prints_the_report(canned) -> None:
    result = runner.invoke(cli.app, ["run", "--json"])
    assert result.exit_code == 0, result.output
    assert (
        json.loads(result.output)["metrics"]["hit_rate"]
        == canned.report["metrics"]["hit_rate"]
    )


def test_write_baseline_writes_the_committed_path(
    canned, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "baseline.json"
    monkeypatch.setattr(cli, "DEFAULT_BASELINE", target)
    result = runner.invoke(cli.app, ["run", "--write-baseline"])
    assert result.exit_code == 0, result.output
    assert json.loads(target.read_text(encoding="utf-8"))["corpus"]["tree_sha256"] == (
        sha256(b"tree-a").hexdigest()
    )


def test_write_baseline_refuses_a_run_with_errors(
    canned, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    canned.report = _report(errors=1)
    target = tmp_path / "baseline.json"
    monkeypatch.setattr(cli, "DEFAULT_BASELINE", target)
    result = runner.invoke(cli.app, ["run", "--write-baseline"])
    assert result.exit_code == 2
    assert "refusing --write-baseline" in result.output
    assert not target.exists()


def test_write_baseline_refuses_a_drifted_corpus(
    canned, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "baseline.json"
    monkeypatch.setattr(cli, "DEFAULT_BASELINE", target)
    result = runner.invoke(cli.app, ["run", "--write-baseline", "--allow-corpus-drift"])
    assert result.exit_code == 2
    assert "cannot become the committed baseline" in result.output
    assert not target.exists()


def test_run_refuses_an_impossible_configuration() -> None:
    result = runner.invoke(cli.app, ["run", "--top-k", "20", "--max-docs", "10"])
    assert result.exit_code == 2
    assert "invalid configuration" in result.output


def test_compare_exits_zero_for_an_unchanged_report(tmp_path: Path) -> None:
    report = _report()
    baseline = tmp_path / "baseline.json"
    fresh = tmp_path / "fresh.json"
    baseline.write_text(json.dumps(report), encoding="utf-8")
    fresh.write_text(json.dumps(report), encoding="utf-8")
    result = runner.invoke(
        cli.app, ["compare", "--report", str(fresh), "--baseline", str(baseline)]
    )
    assert result.exit_code == 0, result.output
    assert "verdict: unchanged" in result.output


def test_compare_exits_one_on_a_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    fresh = tmp_path / "fresh.json"
    baseline.write_text(json.dumps(_report()), encoding="utf-8")
    fresh.write_text(json.dumps(_report(rank=4)), encoding="utf-8")
    result = runner.invoke(
        cli.app, ["compare", "--report", str(fresh), "--baseline", str(baseline)]
    )
    assert result.exit_code == 1, result.output
    assert f"verdict: {VERDICT_REGRESSED}" in result.output


def test_compare_exits_two_when_incomparable(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    fresh = tmp_path / "fresh.json"
    baseline.write_text(json.dumps(_report()), encoding="utf-8")
    fresh.write_text(json.dumps(_report(corpus="tree-b")), encoding="utf-8")
    result = runner.invoke(
        cli.app, ["compare", "--report", str(fresh), "--baseline", str(baseline)]
    )
    assert result.exit_code == 2, result.output
    assert f"verdict: {VERDICT_INCOMPARABLE}" in result.output


def test_compare_exits_two_on_an_unreadable_report(tmp_path: Path) -> None:
    result = runner.invoke(
        cli.app,
        [
            "compare",
            "--report",
            str(tmp_path / "missing.json"),
            "--baseline",
            str(tmp_path / "missing-baseline.json"),
        ],
    )
    assert result.exit_code == 2
    assert "cannot read report" in result.output


@pytest.mark.parametrize(
    "payload",
    [None, [], 7, "bad", {"schema": "indexed.eval.report.v1", "queries": [None]}],
)
def test_compare_rejects_malformed_json_shapes(tmp_path: Path, payload) -> None:
    baseline = tmp_path / "baseline.json"
    fresh = tmp_path / "fresh.json"
    baseline.write_text(json.dumps(_report()))
    fresh.write_text(json.dumps(payload))
    result = runner.invoke(
        cli.app, ["compare", "--report", str(fresh), "--baseline", str(baseline)]
    )
    assert result.exit_code == 2, result.output
    assert "candidate" in result.output


@pytest.mark.parametrize("value", ["nan", "inf", "-1"])
def test_compare_rejects_invalid_tolerance(tmp_path: Path, value: str) -> None:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report()))
    result = runner.invoke(
        cli.app,
        [
            "compare",
            "--report",
            str(path),
            "--baseline",
            str(path),
            "--tolerance",
            value,
        ],
    )
    assert result.exit_code == 2, result.output
    assert "tolerance" in result.output


def test_compare_reports_json_parse_errors(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{")
    result = runner.invoke(
        cli.app, ["compare", "--report", str(path), "--baseline", str(path)]
    )
    assert result.exit_code == 2
    assert "cannot read report" in result.output


def test_compare_nonfinite_tolerance_json_is_finite(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report()))
    result = runner.invoke(
        cli.app,
        [
            "compare",
            "--report",
            str(path),
            "--baseline",
            str(path),
            "--tolerance",
            "nan",
            "--json",
        ],
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["tolerance"] is None


def test_compare_oversized_json_integer_exits_two(tmp_path: Path) -> None:
    """Convert the interpreter JSON digit limit into an invalid-report CLI result."""
    import sys

    limit = sys.get_int_max_str_digits()
    if not limit:
        pytest.skip("interpreter JSON integer digit limit is disabled")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(_report()))
    candidate = tmp_path / "candidate.json"
    candidate.write_text('{"n": ' + "1" * (limit + 1) + "}")
    result = runner.invoke(
        cli.app, ["compare", "--report", str(candidate), "--baseline", str(baseline)]
    )
    assert result.exit_code == 2
    assert "cannot read report" in result.output


def test_compare_programming_value_error_is_not_input_error(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report()))

    def fail_comparison(*args, **kwargs):
        raise ValueError("comparison programming error")

    monkeypatch.setattr(cli, "compare_reports", fail_comparison)
    result = runner.invoke(
        cli.app, ["compare", "--report", str(path), "--baseline", str(path)]
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, ValueError)
    assert "cannot read report" not in result.output
