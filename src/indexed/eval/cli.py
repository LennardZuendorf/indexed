"""``indexed-eval`` — run and compare the retrieval-eval baseline (issue #204).

Two commands, deliberately small:

* ``indexed-eval run`` builds the pinned corpus, measures the pinned case set and
  writes a report (``--out``); with ``--write-baseline`` it writes the committed
  baseline in place.
* ``indexed-eval compare`` diffs a fresh report against the baseline and exits
  non-zero on a regression, so it can wrap a CI step or a pre-push hook.

Both are offline: the corpus ships in the repo and the default embedding model is
read from the local HuggingFace cache (a cache miss downloads once, which is
provisioning — the report records the cache state).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from indexed.eval.cases import EvalDataError, write_json
from indexed.eval.compare import compare_reports, exit_code, format_summary
from indexed.eval.runner import RunConfig, run_eval

DEFAULT_BASELINE = Path("eval/baseline.json")

app = typer.Typer(
    add_completion=False,
    help="Retrieval evaluation: measure hit-rate/MRR on the pinned case set.",
    no_args_is_help=True,
)


def main() -> None:
    """Console-script entry point (``indexed-eval``)."""
    app()


@app.command("run")
def run_command(
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Write the report here (default: stdout only).",
    ),
    write_baseline: bool = typer.Option(
        False,
        "--write-baseline",
        help="Write eval/baseline.json in place (a deliberate, reviewed change).",
    ),
    cases: Path = typer.Option(
        Path("eval/cases.json"), "--cases", help="Pinned case set."
    ),
    corpus: Path = typer.Option(Path("eval/corpus"), "--corpus", help="Pinned corpus."),
    corpus_manifest: Path = typer.Option(
        Path("eval/corpus.json"), "--corpus-manifest", help="Pinned corpus manifest."
    ),
    top_k: int = typer.Option(5, "--top-k", help="k for hit-rate@k."),
    max_docs: int = typer.Option(
        10, "--max-docs", help="Documents the engine returns."
    ),
    rerank: bool = typer.Option(
        False,
        "--rerank/--no-rerank",
        help="Rerank toggle for this run (pinned in the report; never ambient).",
    ),
    engine: str = typer.Option("2", "--engine", help="Collection engine (1 or 2)."),
    allow_corpus_drift: bool = typer.Option(
        False,
        "--allow-corpus-drift",
        help="Measure even when the corpus differs from its manifest (not comparable).",
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Print the report JSON instead of a summary."
    ),
) -> None:
    """Measure the pinned case set and report hit-rate@k / MRR."""
    try:
        config = RunConfig(top_k=top_k, max_docs=max_docs, rerank=rerank, engine=engine)
    except ValueError as exc:
        typer.echo(f"invalid configuration: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    try:
        report = run_eval(
            cases_path=cases,
            corpus_dir=corpus,
            corpus_manifest=corpus_manifest,
            config=config,
            verify_corpus=not allow_corpus_drift,
        )
    except EvalDataError as exc:
        typer.echo(f"eval data error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if out is not None:
        write_json(out, report)
    if write_baseline:
        # A baseline is a claim about retrieval quality; refuse to commit one that
        # measured nothing (every case errored), that skipped cases, or that was
        # measured against a corpus nobody verified against the pinned manifest.
        metrics = report["metrics"]
        if allow_corpus_drift:
            typer.echo(
                "refusing --write-baseline: --allow-corpus-drift measures a corpus "
                "that differs from eval/corpus.json, so it cannot become the "
                "committed baseline",
                err=True,
            )
            raise typer.Exit(code=2)
        if metrics["hit_rate"] is None or metrics["errors"]:
            typer.echo(
                "refusing --write-baseline: the run measured "
                f"{metrics['answerable']} answerable cases and {metrics['errors']} "
                "errors — fix the run before committing a baseline",
                err=True,
            )
            raise typer.Exit(code=2)
        write_json(DEFAULT_BASELINE, report)

    if as_json:
        typer.echo(json.dumps(report, indent=2))
        return

    metrics = report["metrics"]
    typer.echo(f"corpus   {report['corpus']['tree_sha256'][:12]}")
    typer.echo(
        f"cases    {metrics['answerable']} answerable, "
        f"{metrics['unanswerable']} unanswerable, {metrics['errors']} errors"
    )
    if metrics["hit_rate"] is None:
        typer.echo(f"hit@{metrics['k']}   n/a   mrr n/a  (nothing measured)")
    else:
        typer.echo(
            f"hit@{metrics['k']}   {metrics['hit_rate']:.3f}   mrr {metrics['mrr']:.3f}"
        )
    typer.echo(
        f"model    {report['config']['embedding_model']} "
        f"({report['config']['score_kind'] or 'unknown'} scores)"
    )
    if metrics["failed_by_id"]:
        typer.echo(f"failures {', '.join(metrics['failed_by_id'])}")
    if out is not None:
        typer.echo(f"report   {out}")


@app.command("compare")
def compare_command(
    report: Path = typer.Option(..., "--report", help="Fresh report to judge."),
    baseline: Path = typer.Option(
        DEFAULT_BASELINE, "--baseline", help="Committed baseline to compare against."
    ),
    tolerance: float = typer.Option(
        0.0, "--tolerance", help="Absolute metric delta treated as noise."
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the comparison JSON."),
) -> None:
    """Compare a report against the baseline; exit 1 on a regression."""
    from indexed.eval.compare import load_report

    try:
        baseline_report = load_report(str(baseline))
        candidate_report = load_report(str(report))
    except (OSError, ValueError) as exc:
        typer.echo(f"cannot read report: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    result = compare_reports(baseline_report, candidate_report, tolerance=tolerance)
    if as_json:
        typer.echo(json.dumps(result, indent=2))
    else:
        typer.echo(format_summary(result))
    raise typer.Exit(code=exit_code(result))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
