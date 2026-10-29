---
type: feature-plan
feature: retrieval-eval
sibling: tech.md
parent: ../../plan.md
updated: 2026-10-29
---

# Feature: Retrieval Evaluation Baseline — Implementation Plan

One delivery, one reviewable unit: pinned corpus + pinned case set + harness +
measured baseline + tests + runbook. It has no graph dependency on the feature
work, so it lands in parallel with everything else.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)
**Runbook:** [../../../eval/README.md](../../../eval/README.md)

**Feature gate:** Delivered — `src/indexed/eval/`, `indexed-eval` console script,
`eval/{corpus,corpus.json,cases.json,baseline.json,README.md}`,
`scripts/build_eval_corpus.py`, `tests/unit/indexed/eval/`.

---

## Units (all closed in this delivery)

1. **Metric arithmetic first, test-first.** `eval/metrics.py` + its tests, so the
   definitions exist before any engine call can influence them. Explicitly
   defined: hit@k, MRR, duplicates/ties, empty results, errors, unanswerable.
2. **Pinned corpus.** `scripts/build_eval_corpus.py` copies 11 repo documents into
   `eval/corpus/` and writes `corpus.json` with per-file `sha256`, a tree hash and
   the source revision; `--check` fails on drift.
3. **Pinned case set.** 15 verbatim GitHub issue titles, 11 answerable + 4
   unanswerable, each with provenance, rationale, expected documents, near-miss
   distractors and the anchor that justifies the judgement. Validated on load.
4. **Adapter.** One seam from the facade result to ranked hits, so a ratified
   #109 envelope touches one module.
5. **Runner.** Build the corpus in a temp collections dir, run the cases, emit the
   report with configuration + environment + per-query rankings + trusted-context
   failures kept out of the denominators.
6. **Baseline + comparison.** `indexed-eval run --write-baseline` commits the
   first measurement; `indexed-eval compare` returns improved / regressed /
   unchanged / incomparable with exit codes 0 / 1 / 2.
7. **Tests.** 43 tests across metrics, cases, adapter, compare and runner,
   including a gated real-model test that asserts the committed baseline
   reproduces.

## Follow-ups, deliberately not in this delivery

- **CI gating.** `.github/workflows/python-eval.yml` runs the measurement and the
  comparison on retrieval-affecting PRs today, but `continue-on-error: true`: it
  reports the verdict and uploads the artifacts without blocking a merge. Turning
  it into a gate needs a tolerance from observed run-to-run variance — one
  baseline run cannot separate signal from noise.
- **Wider corpus.** Code retrieval and GitHub issue/PR text need their own pinned
  corpus and judgements — the roadmap's "coding-agent evidence" outcome is not
  measured by this documentation corpus.
- **Chunk-level judgement.** The harness currently judges documents; whether the
  *chunk* handed to an agent is useful is the next question, and it belongs with
  context expansion (#219).
- **#205 consumption.** Hybrid BM25+vector fusion compares its per-query results
  against this harness; the artifact contract (per-query ranked ids, score kind,
  elapsed time, configuration) is what it asked for.
