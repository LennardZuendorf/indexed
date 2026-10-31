"""End-to-end harness behaviour: report shape, failures, baseline reproducibility.

The mechanics run model-free (``MockEmbedding``), because the interesting claims
are structural: the corpus gets pinned, errors stay out of the denominators, and
the report carries what a later comparison needs. Reproducing the committed
baseline needs the real embedding model and is gated on the local cache.
"""

from __future__ import annotations

import json
import platform
import shutil
import sys
from pathlib import Path

import pytest

from indexed.eval.compare import VERDICT_UNCHANGED, compare_reports
from indexed.eval.runner import RunConfig, run_eval

from tests.conftest import model_available
from tests.unit.indexed.core.v2._engine_helpers import mock_embedding


def _mini_cases(path: Path, corpus_dir: Path, *, query: str) -> Path:
    """Write one answerable and one unanswerable case bound to real corpus names."""
    payload = {
        "schema": "indexed.eval.cases.v1",
        "description": "two-case subset for the harness mechanics",
        "corpus_id": "indexed-docs",
        "cases": [
            {
                "id": "answered",
                "query": query,
                "provenance": "GitHub issue #1 title",
                "rationale": "the harness needs one answerable case",
                "relevant": sorted(p.name for p in corpus_dir.iterdir())[:1],
                "distractors": [],
            },
            {
                "id": "unanswerable",
                "query": "a question this corpus cannot answer",
                "provenance": "GitHub issue #2 title",
                "rationale": "the harness needs one unanswerable case",
                "relevant": [],
                "distractors": [sorted(p.name for p in corpus_dir.iterdir())[0]],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.integration
def test_run_eval_emits_a_report_pinned_to_corpus_case_set_and_config(
    tmp_path: Path, eval_dir: Path
) -> None:
    """Exercise report evidence assembly with mock embeddings instead of model quality."""
    cases = _mini_cases(
        tmp_path / "cases.json", eval_dir / "corpus", query="retrieval configuration"
    )
    with mock_embedding(embed_dim=8):
        report = run_eval(
            cases_path=cases,
            corpus_dir=eval_dir / "corpus",
            corpus_manifest=eval_dir / "corpus.json",
            collections_path=tmp_path / "collections",
            config=RunConfig(top_k=5, max_docs=10),
        )

    assert report["schema"] == "indexed.eval.report.v1"
    assert len(report["corpus"]["tree_sha256"]) == 64
    assert len(report["case_set"]["sha256"]) == 64
    assert report["case_set"]["cases"] == 2
    assert report["config"]["top_k"] == 5
    assert report["config"]["embedding_model"]
    assert report["failures"] == []

    metrics = report["metrics"]
    assert metrics["answerable"] == 1
    assert metrics["unanswerable"] == 1
    assert metrics["errors"] == 0
    assert set(metrics) >= {"hit_rate", "mrr", "k", "cases"}

    records = {record["id"]: record for record in report["queries"]}
    assert records["answered"]["status"] == "scored"
    assert records["answered"]["provenance"] == "GitHub issue #1 title"
    assert records["answered"]["elapsed_ms"] >= 0
    assert records["unanswerable"]["status"] == "unanswerable"
    # A document ranking is part of the evidence, whatever the model does.
    assert isinstance(records["answered"]["ranking"], list)
    assert report["environment"]["embedding_model_cache"]["cache_dir"]


@pytest.mark.integration
def test_a_collection_error_is_a_recorded_failure_not_a_miss(
    tmp_path: Path, eval_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prevent retrieval infrastructure failures from lowering measured hit rate."""
    cases = _mini_cases(
        tmp_path / "cases.json", eval_dir / "corpus", query="retrieval configuration"
    )

    def _broken_search(query, collections_path, config):
        return {config.collection: {"error": "collection manifest is unreadable"}}

    monkeypatch.setattr("indexed.eval.runner._search_one", _broken_search)
    with mock_embedding(embed_dim=8):
        report = run_eval(
            cases_path=cases,
            corpus_dir=eval_dir / "corpus",
            corpus_manifest=eval_dir / "corpus.json",
            collections_path=tmp_path / "collections",
            config=RunConfig(),
        )

    metrics = report["metrics"]
    assert metrics["errors"] == 2
    assert metrics["answerable"] == 0
    # No scored case is no measurement: None, never a fabricated 0.0 (metrics.py).
    assert metrics["hit_rate"] is None
    assert metrics["mrr"] is None
    assert metrics["failed_by_id"] == ["answered", "unanswerable"]
    assert [failure["id"] for failure in report["failures"]] == [
        "answered",
        "unanswerable",
    ]
    assert "unreadable" in report["failures"][0]["error"]


@pytest.mark.integration
@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_missing_or_corrupt_real_collection_is_excluded(
    tmp_path, eval_dir, monkeypatch, damage
):
    """Check real facade failures cannot become scored misses or unanswerable cases."""
    from indexed.eval.runner import build_collection

    cases = _mini_cases(tmp_path / "cases.json", eval_dir / "corpus", query="query")

    def damaged_build(corpus_dir, collections_path, config, **kwargs):
        """Build a real collection before injecting the selected persistence failure."""
        build_collection(corpus_dir, collections_path, config, **kwargs)
        collection = collections_path / config.collection
        if damage == "missing":
            shutil.rmtree(collection)
        else:
            (collection / "manifest.json").write_text("{invalid JSON")

    monkeypatch.setattr("indexed.eval.runner.build_collection", damaged_build)
    with mock_embedding(embed_dim=8):
        report = run_eval(
            cases_path=cases,
            corpus_dir=eval_dir / "corpus",
            corpus_manifest=eval_dir / "corpus.json",
            collections_path=tmp_path / "collections",
        )
    assert report["metrics"]["errors"] == 2
    assert report["metrics"]["answerable"] == report["metrics"]["unanswerable"] == 0
    assert report["metrics"]["hit_rate"] is report["metrics"]["mrr"] is None
    assert {item["id"] for item in report["failures"]} == {"answered", "unanswerable"}


@pytest.mark.unit
def test_corpus_drift_fails_the_run_before_it_measures(
    tmp_path: Path, eval_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prevent collection construction from consuming bytes outside the pinned corpus."""
    from indexed.eval.cases import EvalDataError

    cases = _mini_cases(
        tmp_path / "cases.json", eval_dir / "corpus", query="retrieval configuration"
    )
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for source in (eval_dir / "corpus").iterdir():
        (corpus / source.name).write_bytes(source.read_bytes())
    (corpus / "lessons.md").write_text("hand edit", encoding="utf-8")

    def forbidden_build(*args, **kwargs):
        pytest.fail("corpus drift reached collection build")

    monkeypatch.setattr("indexed.eval.runner.build_collection", forbidden_build)
    with pytest.raises(EvalDataError, match="drift"):
        run_eval(
            cases_path=cases,
            corpus_dir=corpus,
            corpus_manifest=eval_dir / "corpus.json",
            collections_path=tmp_path / "collections",
        )


@pytest.mark.slow
@pytest.mark.integration
def test_the_committed_baseline_reproduces(
    tmp_path: Path, eval_dir: Path, eval_model_cache: Path
) -> None:
    """The whole point: the committed numbers are reproducible on demand."""
    baseline = json.loads((eval_dir / "baseline.json").read_text(encoding="utf-8"))
    if not model_available():
        pytest.skip("Embedding model not cached (all-MiniLM-L6-v2)")

    report = run_eval(
        cases_path=eval_dir / "cases.json",
        corpus_dir=eval_dir / "corpus",
        corpus_manifest=eval_dir / "corpus.json",
        collections_path=tmp_path / "collections",
    )

    assert report["corpus"]["tree_sha256"] == baseline["corpus"]["tree_sha256"]
    assert report["case_set"]["sha256"] == baseline["case_set"]["sha256"]
    # The comparison calls a config difference "incomparable", so a default that
    # drifts from the committed one must fail here rather than at CI's verdict
    # (a `--rerank` default of "unset" vs `False` did exactly that).
    assert report["config"] == baseline["config"]
    if (sys.version.split()[0], platform.platform()) != (
        baseline["environment"]["python"],
        baseline["environment"]["platform"],
    ):
        pytest.skip("Exact baseline rankings require the recorded Python/platform")
    for key in ("numerical_dependencies", "embedding_model_cache"):
        if key not in baseline["environment"]:
            continue
        expected = baseline["environment"][key]
        actual = report["environment"][key]
        if key == "embedding_model_cache":
            expected = expected.get("selected_snapshot")
            actual = actual.get("selected_snapshot")
        if expected != actual:
            pytest.skip(f"Exact baseline rankings require the recorded {key}")
    assert report["metrics"]["hit_rate"] == baseline["metrics"]["hit_rate"]
    assert report["metrics"]["mrr"] == baseline["metrics"]["mrr"]
    assert [record["ranked_docs"] for record in report["queries"]] == [
        record["ranked_docs"] for record in baseline["queries"]
    ]

    verdict = compare_reports(baseline, report)
    assert verdict["verdict"] == VERDICT_UNCHANGED
    assert verdict["comparable"] is True


@pytest.mark.parametrize("mutation", ["corpus_id", "relevant", "distractors"])
@pytest.mark.unit
def test_case_corpus_binding_is_refused_before_build(
    tmp_path, eval_dir, monkeypatch, mutation
):
    """Reject mismatched corpus identity or unknown judgments before collection work."""
    from indexed.eval.cases import EvalDataError

    cases = _mini_cases(tmp_path / "cases.json", eval_dir / "corpus", query="query")
    payload = json.loads(cases.read_text())
    if mutation == "corpus_id":
        payload["corpus_id"] = "other"
    else:
        payload["cases"][0][mutation] = ["unknown.md"]
    cases.write_text(json.dumps(payload))

    def forbidden_build(*args, **kwargs):
        pytest.fail("invalid judgments reached collection build")

    monkeypatch.setattr("indexed.eval.runner.build_collection", forbidden_build)
    with pytest.raises(EvalDataError, match=mutation):
        run_eval(
            cases_path=cases,
            corpus_dir=eval_dir / "corpus",
            corpus_manifest=eval_dir / "corpus.json",
        )


@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        "bad",
        {"eval-corpus": []},
        {"eval-corpus": {"results": [None]}},
        {"eval-corpus": {"results": [{"id": "a.md", "matchedChunks": [False]}]}},
        *[
            {"eval-corpus": {"error": value, "results": []}}
            for value in ([], {}, False, 0)
        ],
    ],
)
@pytest.mark.unit
def test_malformed_search_is_excluded_and_cannot_be_a_baseline(
    tmp_path, eval_dir, monkeypatch, result
):
    """Keep malformed retrieval evidence out of metric denominators and baseline files."""
    from typer.testing import CliRunner
    from indexed.eval.cli import app

    cases = _mini_cases(tmp_path / "cases.json", eval_dir / "corpus", query="query")
    monkeypatch.setattr(
        "indexed.eval.runner.build_collection", lambda *args, **kwargs: None
    )
    monkeypatch.setattr("indexed.eval.runner._search_one", lambda *args: result)
    report = run_eval(
        cases_path=cases,
        corpus_dir=eval_dir / "corpus",
        corpus_manifest=eval_dir / "corpus.json",
    )
    assert report["metrics"]["errors"] == 2
    assert report["metrics"]["answerable"] == report["metrics"]["unanswerable"] == 0
    assert report["metrics"]["hit_rate"] is report["metrics"]["mrr"] is None
    baseline = tmp_path / "baseline.json"
    monkeypatch.setattr("indexed.eval.cli.DEFAULT_BASELINE", baseline)
    outcome = CliRunner().invoke(
        app,
        [
            "run",
            "--cases",
            str(cases),
            "--corpus",
            str(eval_dir / "corpus"),
            "--corpus-manifest",
            str(eval_dir / "corpus.json"),
            "--write-baseline",
        ],
    )
    assert outcome.exit_code == 2
    assert "refusing --write-baseline" in outcome.output
    assert not baseline.exists()
