---
type: feature-tech
feature: retrieval-eval
sibling: product.md
parent: ../../tech.md
updated: 2026-11-06
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
refused before anything is measured. `answered_by` is `file:line`,
`file:first-last` or a comma-separated list (a bare number keeps the previous
file); the loader cannot resolve it — it has no corpus path — so the test suite
resolves every anchor against the pinned copy and fails on a line that is out of
range, blank, or outside the case's relevant documents.
These structural checks do not establish semantic relevance; fixture review
must confirm that the cited text supports the judgment.

Artifact loaders reject malformed JSON, wrong container/field types, ambiguous
document identities and invalid flat paths with `EvalDataError`. Case and corpus
IDs must match before a build. Every indexed file must be a declared regular
file; nested or unpinned content is refused. Malformed retrieval envelopes are
trusted-context failures, excluded from denominators and baseline writing.

`eval/corpus.json` — `{schema: indexed.eval.corpus.v1, corpus_id,
source_repo_rev, tree_sha256, files[{path, source, sha256, bytes}]}`.
`tree_sha256` hashes the sorted `"<sha256>  <name>\n"` lines, so it is cheap to
recompute and changes on any byte change. The runner verifies it by default; a
drifted corpus is an error, not a footnote.
Code and docs are copied from the stated Git revision. Sanitized GitHub extracts
are local snapshot inputs with separate upstream URL, capture revision/time,
sanitization notes and content hash; transformed bytes do not claim Git origin.

`eval/baseline.json` — `indexed.eval.report.v1`: `case_set{path, sha256, cases}`,
`corpus{tree_sha256, source_repo_rev, files[]}`, `config{engine, embedding_model,
score_kind, rerank, top_k, max_docs}`, `environment{python, platform,
indexed_version, embedding_model_cache{cache_dir, present, weights,
selected_snapshot, snapshot_path}}`,
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

- Same corpus, model, config and numerical environment are the reproduction
  boundary. The real-model test checks saved rankings and metrics within that
  environment; metric recomputation from saved rankings is deterministic.
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

Comparison validates each report before arithmetic: experiment hashes/config,
unique query identities, internally reconciled counts/failures, and metrics
derived from saved rankings. All baseline query IDs must remain present;
candidate-only errors remain reportable regressions. Tolerances must be finite
and nonnegative. Dense/rerank experiments retain configuration incomparability.
Both model identities, effective settings and cache snapshots are recorded.

## Testing

`tests/unit/indexed/eval/`:

- metric arithmetic and every edge case (multiple relevant targets, duplicates,
  empty results, errors, unanswerable, recomputation identity) — model-free;
- case-set and corpus-manifest validation + drift refusal, including every
  `answered_by` anchor resolving in the pinned corpus (in range, non-blank, into a
  document the case judges relevant) — a stale line reference fails the suite
  instead of silently justifying nothing;
- adapter flattening (fake payloads, `file://` ids, error payloads);
- Local baseline comparison verdicts and exit codes: a metric drop, a per-case rank drop (even
  when a compensating case leaves the average flat), a newly errored case, or a
  rise in `distractor_leak` all mean `regressed` (exit 1) — the unanswerable
  cases are part of the gate, not a footnote;
- runner mechanics under `MockEmbedding` (report shape, failure classification,
  drift refusal) — the `MockEmbedding` path proves structure, not ranking, since
  all its scores tie;
- one real-model test resolves availability after installing its explicit cache
  fixture, checks corpus/case/config identity, then checks exact reproduction
  only for matching Python/platform, numerical dependencies and model snapshot.

Effective report settings include embedding batch size, score threshold and
reranker identity/top-n. `ConfigService.temporary_overlay` restores prior values
after every run; unrelated connector/MCP and other-engine sections are masked
inside that scope. Both model caches record usable selected snapshot identity.
Environment provenance includes numerical package versions, Git head, dirty
status and a source/dependency fingerprint for measurements before a commit.

## CI reporting

The evaluation workflow consumes its existing report/comparison JSON through
`.github/scripts/eval-comment.cjs`. A pinned GitHub Script action writes a job
summary, then creates or updates the bot comment marked `indexed:retrieval-eval`.
Show metrics, verdict, changed ranks, failure IDs, source commits and run links;
highlight environment/config differences and unavailable reports.

Repository contents stay read-only. PR comment permission is job-scoped;
comments target same-repository PRs only. Fork/manual runs keep summaries and
artifacts. Paginate comments, match marker plus bot identity, and check the
current PR head before posting. Escape report-derived text. Posting failures
produce a warning without changing phase-one evaluation semantics.

## Same-job gate and canonical context

`python-eval.yml` measures the captured event base and its corresponding PR
merge result in one job. It fetches immutable SHAs, verifies both merge parents,
and verifies each measured HEAD. Each side uses its own detached worktree and
`uv sync --locked` environment. Dispatch measures its captured revision twice;
it never resolves a moving branch tip. The common launcher is captured once
from the merge result and runs by absolute path through each side's own Python.

`scripts/eval_ab_run.py` calls the side's existing `run_eval(connector_factory=...)`
API. It loads only the shared `eval/canonical.py` helper by explicit file path.
The side retains its own evaluator runner, core, parser, connectors and lock.
Actual import origins must be inside that side. Reports record full engine and
harness SHAs, lock digest, common-file digests and whether instrumentation
matches its captured commit. Local uncommitted instrumentation says so. Report outputs reject nonregular
paths with `lstat` and use exclusive temporary descriptors plus atomic replacement.

The evaluator-only converter replaces recognized generated leading absolute
code/plaintext path context with `eval/corpus/<relative path>`. It preserves
authored body occurrences, headings, chunk boundaries, IDs and physical
URLs/metadata. The default local evaluator uses the same canonical factory;
explicit custom factories remain supported. Effective configuration records
`input_context_policy=eval-corpus-relative-v1` (or `custom`).

`environment.converter_inputs` hashes normalized converter chunks with the
boundary label `normalized-converter-chunks`. It does not claim to capture
post-engine embedding inputs. Equal digests are checked during same-source
stability validation; intentional parser/engine changes may change inputs.

One comparator validates complete saved reports with
`indexed.eval.report_validation.report_problems` before metrics or fingerprints.
Both sides require every selected metric, identical query identities/judgments,
full effective model/score configuration, selected model snapshots, complete
CPU/system/Python identities and matching common instrumentation. Invalid
containers, missing evidence, nonfinite/unrepresentable numbers and invalid
tolerance exit 2 with an invalid-result JSON and no verdict. Regressions exit 1;
valid within-policy measurements exit 0. The publisher consumes this sole verdict.

The retained policy is **0.04 absolute points** for hit-rate@k and MRR.
Distractor leakage remains report-only. Historical CI measured 0.0307 MRR
movement at the two-environment boundary; that observation did not diagnose its
cause. A later controlled local experiment isolated generated absolute path
prefixes: changing only 77 inputs moved one relevant rank 5 to 6. Canonical
context fixes that demonstrated harness cause without a product retrieval
change or wider tolerance. Bounded local same-source validation is separate
from hosted acceptance and is not a universal determinism guarantee.

The committed `eval/baseline.json` remains a historical drift reference, with
its original physical-path context. Exact reproduction requires the same input
policy and numerical environment. CI compares its two fresh reports instead.
Machine-block adoption for legacy reports still requires matching the actual
job platform and never overwrites an explicit recorded machine block.

Both reports and `eval-ab.json` are uploaded. A failed harness blocks
measurement; the publisher still displays unavailable phases and preserves
failures. The publisher step alone is advisory. Fork/manual runs retain summary
and artifacts. Dispatch `variance_repeats` accepts integers 1 through 10.


Gate identity validation requires a present model's nonempty selected snapshot
and weights. Active reranking also requires its model name and valid cache;
an absent inactive reranker remains compatible. Common instrumentation, when
present, must include a full revision, matching effective normalization policy,
and exactly two valid SHA256 digests for launcher and canonical helper.
CI passes `--require-common-harness`; ordinary local/legacy reports may omit
that instrumentation. Errored queries invalidate the gate rather than reducing
its metric denominators.

Measurement setup/base/head/repeat failures exit 2 through the shared error
trap. They do not synthesize a verdict artifact: the publisher shows the failed
measurement phase and unavailable verdict. Comparator input-read, host-adoption
and report-validation failures write an explicit invalid-result artifact.


The publisher validates comparator-invalid artifacts separately from pass/fail
artifacts. Early failures may contain label-only sides and null tolerance;
unknown identity fields render as unavailable, while escaped reasons retain the
invalid status. Pass/fail still requires complete machine/interpreter sides.
Invalid reasons are limited to ten displayed entries with bounded text and an
artifact link for omitted content; invalid artifacts show no gating table.
