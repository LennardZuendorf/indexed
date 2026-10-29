---
type: feature-tech
feature: retrieval-eval
sibling: product.md
parent: ../../tech.md
updated: 2026-10-29
---

# Feature: Retrieval Evaluation Baseline — Architecture

A new top layer package `src/indexed/eval/` that consumes core **only through the
`indexed.core.engine` facade** — the same entry point the CLI and the MCP server
use — plus two committed data artifacts (`eval/corpus/` + `eval/cases.json`) and a
committed report (`eval/baseline.json`). No new engine code, no new retrieval
path, no LLM, no network beyond the local embedding-model cache.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

---

## Why the facade, and why document-level

The harness measures the *retrieval contract*, so it reads the raw facade result
(`core/v2/retrieval.py:222-227` per collection: `collectionName`, `indexerName`,
`scoreKind`, `results`; per document `id`/`url`/`path`/`matchedChunks`; per chunk
`chunkNumber`/`score`). That layer is stable today and carries the two things a
metric needs — document identity (`id`) and rank order.

The presentation envelope is *not* stable: #108/#109 has two uncommitted,
mutually incompatible drafts in flight (flat `indexed.search.v1` with no document
id vs document-grouped `indexed.search/1`). Pinning the harness to either would
pin it to a draft, and the flat draft cannot express a document-level rank at
all. So `eval/adapter.py` is the single seam that knows the dialect; when #109
ratifies an envelope, only that module changes.

## Modules

| Module | Responsibility |
|---|---|
| `eval/metrics.py` | Pure arithmetic: rank normalisation, hit@k, reciprocal rank, aggregation. No I/O, no ML. The definitions live in its docstring. |
| `eval/cases.py` | Load + validate `cases.json`; hash the corpus and refuse drift against `corpus.json`. |
| `eval/adapter.py` | Facade result → ranked `Hit`s; the only place that knows field names. |
| `eval/runner.py` | Build the pinned corpus into a throwaway collections dir, run every case, assemble the report. |
| `eval/compare.py` | Baseline vs candidate: metric deltas, per-case rank movement, verdict, exit code. |
| `eval/cli.py` | `indexed-eval run` / `indexed-eval compare`. |

## Data contracts

`eval/cases.json` — `{schema: indexed.eval.cases.v1, corpus_id, cases[]}` where a
case carries `id, query, provenance, rationale, relevant[], distractors[],
answered_by`. Validation is strict: an empty query, a duplicate id, a missing
provenance or rationale, or a document listed as both relevant and distractor is
refused before anything is measured.

`eval/corpus.json` — `{schema: indexed.eval.corpus.v1, corpus_id,
source_repo_rev, tree_sha256, files[{path, source, sha256, bytes}]}`.
`tree_sha256` hashes the sorted `"<sha256>  <name>\n"` lines, so it is cheap to
recompute and changes on any byte change. The runner verifies it by default; a
drifted corpus is an error, not a footnote.

`eval/baseline.json` — `indexed.eval.report.v1`: `case_set{path, sha256, cases}`,
`corpus{tree_sha256, source_repo_rev, files[]}`, `config{engine, embedding_model,
score_kind, rerank, top_k, max_docs}`, `environment{python, platform,
indexed_version, embedding_model_cache{dir, present, weights}}`,
`metrics{hit_rate, mrr, answerable, unanswerable, errors, k}`,
`queries[]{id, query, provenance, rationale, relevant, distractors,
ranked_docs[], ranking[{rank, doc, chunk, score, score_kind}],
first_relevant_rank, reciprocal_rank, hit_at_k, distractor_leak, status,
elapsed_ms, error}`, `failures[]`.

Metric semantics (full text in `metrics.py`): document-level ranking with first
occurrence winning; hit@k truncated, reciprocal rank not; ties keep engine order;
collection errors are trusted-context failures excluded from the denominators;
unanswerable cases are scored only on `distractor_leak`.

## Determinism boundaries

- Same corpus + same model + same config ⇒ identical rankings, scores (6 dp) and
  metrics; only `generated_at` and `elapsed_ms` differ. Verified by running the
  harness twice and by the gated test that reproduces `eval/baseline.json`.
- Model drift is *not* disguised as determinism: the model id, the score kind and
  the cache location/weights are recorded in every report, and a report whose
  configuration differs keeps its numbers but shows `config_changes`.
- Comparability is gated on corpus tree hash **and** case-set hash; anything else
  is `incomparable` (exit 2).
- Every knob is a pinned value, never "unset, use ambient": `rerank` is an
  explicit `bool` (`False` by default) in both `RunConfig` and `--rerank/--no-rerank`,
  because an `Optional[bool]` default of `None` was recorded as `rerank: null` and
  made an otherwise identical run report `incomparable`. The gated test asserts the
  whole `config` block equals the committed baseline's, not just the model.

## Testing

`tests/unit/indexed/eval/`:

- metric arithmetic and every edge case (multiple relevant targets, duplicates,
  empty results, errors, unanswerable, recomputation identity) — model-free;
- case-set and corpus-manifest validation + drift refusal;
- adapter flattening (fake payloads, `file://` ids, error payloads);
- Comparison verdicts and exit codes: a metric drop, a per-case rank drop (even
  when a compensating case leaves the average flat), a newly errored case, or a
  rise in `distractor_leak` all mean `regressed` (exit 1) — the unanswerable
  cases are part of the gate, not a footnote;
- runner mechanics under `MockEmbedding` (report shape, failure classification,
  drift refusal) — the `MockEmbedding` path proves structure, not ranking, since
  all its scores tie;
- one gated real-model test that reruns the pinned set and asserts the committed
  baseline reproduces (`skipif not model_available()`).
