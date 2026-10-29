# Retrieval evaluation baseline

Measured retrieval, not vibes. This directory holds a pinned corpus, a pinned
set of judged queries, and the baseline numbers every later retrieval change is
compared against — reranking, hybrid BM25+vector (#205), chunking, graph scoring.

What this is **not**: a claim about answer quality, faithfulness or task success.
It measures one thing — *does the right document reach the top of the ranking* —
against one corpus. Generated answers, LLM judges and cloud APIs are out of
scope on purpose (both would add a second moving part to a number that only
needs to detect movement).

## Contents

| Path | What it is |
|---|---|
| `eval/corpus/` | The pinned corpus: 11 Markdown documents copied from this repo. |
| `eval/corpus.json` | Manifest: `sha256` per file, `tree_sha256`, and the source repo revision. |
| `eval/cases.json` | The case set: 15 queries, 11 answerable + 4 deliberately unanswerable. |
| `eval/baseline.json` | The committed baseline report (numbers + per-query rankings). |
| `scripts/build_eval_corpus.py` | Rebuilds `eval/corpus/` + `eval/corpus.json` from the repo (`--check` for drift). |

Code lives in `src/indexed/eval/` and is exposed as the `indexed-eval` command.

## Provenance

**Corpus** — a *copy*, never a reference: a doc edit in the repo must not silently
move the baseline. The 11 documents are the project's own documentation
(`README.md`, `AGENTS.md`, `.spec/*.md`) at
`source_repo_rev 89a6cb0a5589d5d20ea9ae0676fcd427cc40dbf1`, tree hash
`1343091323763f5a18c9d5eb44d0461408d8718688ec5e8118ae26d7a2fca533`. Every entry
in `corpus.json` records the repo file it came from. `source_repo_rev` names the
revision the branch was based on: the copy is taken from the working tree as it
ships, so the per-file `sha256` values — which every run verifies — are the
binding record, not the rev label.

**Queries** — every query is a verbatim GitHub issue title from
`LennardZuendorf/indexed`; the issue number is recorded per case. Nothing is
invented to make the benchmark look good, and no query was written after seeing
what the retriever returned.

**Judgements** — each case lists the documents that genuinely answer it, the
near-miss documents that do not, a rationale, and the anchor (`answered_by`) that
justifies the call. Documents are matched by file name, so a judgement survives a
corpus move.

Four cases are **deliberately unanswerable** — an LSP server, a time-travel
search mode, the LOC size gate, and this harness itself. A benchmark made only of
answerable questions flatters a retriever that always returns something; these
four make that behaviour visible.

## Metrics

Defined once, in `src/indexed/eval/metrics.py`:

- **hit-rate@k** — fraction of answerable cases whose relevant document is ranked
  at or above `k` (default `k = 5`).
- **MRR** — mean of `1/rank` of the first relevant document, over the whole
  returned ranking (not truncated at `k`); `0.0` when nothing relevant is
  returned.
- **Ties and duplicates** — the engine's order is the ranking; a document keeps
  its first rank. No tie-break is invented, so recomputing metrics from a saved
  ranking is identical by construction.
- **Errors** — a collection that fails to load is a *trusted-context failure*:
  excluded from both denominators and counted in `errors`, never scored as a miss.
- **Unanswerable cases** — never enter hit-rate or MRR. They report
  `distractor_leak`: whether a near-miss document reached the top `k`.

## Baseline (measured 2026-10-29)

```
corpus   134309132376 (11 documents, tree pinned)
cases    11 answerable, 4 unanswerable, 0 errors
hit@5    0.818      mrr 0.578
model    sentence-transformers/all-MiniLM-L6-v2, cosine scores, rerank off
engine   v2, max_docs 10, top_k 5
latency  431 ms mean per query (406–547 ms, local CPU, model already loaded)
```

Per case (`rank` = rank of the first relevant document, `—` = outside `max_docs`):

| Case (GitHub issue) | Expected | Rank |
|---|---|---|
| #205 hybrid search: BM25 + vector fusion | `plan.md` | 4 |
| #112 MCP server serves stale collections | `tech.md`, `tech-app.md` | 1 |
| #125 wrap v2 errors as CoreV2Error | `lessons.md` | 2 |
| #186 engine-routing correctness gaps | `lessons.md` | 1 |
| #123 jira attachment credentials | `tech-connectors.md` | 1 |
| #61 migrate files parsing to Docling | `tech-parsing.md`, `README.md` | 3 |
| #63 smart model caching | `lessons.md` | 2 |
| #211 duplicate HuggingFace warning | `lessons.md` | 2 |
| #66 pluggable embedding model | `plan.md` | **9 — miss at k=5** |
| #185 `index create` flips a collection's engine | `tech.md`, `tech-core.md` | **6 — miss at k=5** |
| #109 improve CLI search output | `tech-app.md` | 1 |
| #241 `indexed lsp` (unanswerable) | — | distractor leak |
| #204 retrieval eval harness (unanswerable) | — | distractor leak |
| #147 time-travel search (unanswerable) | — | distractor leak |
| #216 LOC size gate (unanswerable) | — | distractor leak |

Reading it honestly: dense retrieval finds the right document for 9 of 11
answerable questions inside the top 5, and both misses sit just outside the cut
(rank 6 and rank 9) rather than nowhere. Both misses are questions whose answer
lives in a *roadmap/decision* document that shares vocabulary with the technical
reference docs — the classic case for hybrid lexical matching (#205). And
`distractor_leak` is 4/4: the retriever never returns "nothing found", it always
fills the top 5, which is exactly what a benchmark needs to keep in view.

## Running it

```bash
# Measure and print the numbers (needs the local embedding model; no keys, no network)
uv run indexed-eval run --out /tmp/eval-report.json

# Compare a fresh run against the committed baseline:
# exit 0 = unchanged/improved, 1 = regressed, 2 = not comparable
uv run indexed-eval run --out /tmp/eval-report.json && \
  uv run indexed-eval compare --report /tmp/eval-report.json

# The same comparison as a test (skips when the model is not cached)
uv run pytest tests/unit/indexed/eval -q
```

A run builds the pinned corpus into a throwaway collections directory, so it
never touches `~/.indexed`. The embedding model is read from the local
HuggingFace cache; the report records the cache directory and whether weights
were present, so a first-run download reads as provisioning, not as a metric
change.

## Reproducibility

Two consecutive runs over the same corpus and model produce identical rankings,
scores and metrics — only `generated_at` and `elapsed_ms` differ. The gated test
`tests/unit/indexed/eval/test_runner.py::test_the_committed_baseline_reproduces`
asserts exactly that against `eval/baseline.json`.

A report is comparable to another only when the corpus tree hash **and** the case
set hash **and** the retrieval configuration all match; anything else is reported
as `incomparable` (exit 2) instead of being dressed up as a regression or an
improvement. A model swap or a `max_docs` change moves the numbers without being a
ranking win, so it is never scored as one — the difference is listed under
`config_changes` next to the metric delta for the human to read.

A comparable run fails (exit 1) when a metric drops, when a case that used to be
found moves *down* (even if another case compensates and the average is flat),
when a case newly errors, or when `distractor_leak` rises. The unanswerable cases
are part of the gate, not decoration.

## Changing the baseline

The baseline moves only deliberately:

1. Change the retrieval code or configuration and measure:
   `uv run indexed-eval run --out /tmp/new.json`.
2. Compare: `uv run indexed-eval compare --report /tmp/new.json`. The per-case
   `improved` / `regressed` lists say *which* queries moved, not just whether the
   average did.
3. If the change is intended, commit the new baseline
   (`uv run indexed-eval run --write-baseline`) in the same PR as the change and
   say why in the PR body.

Corpus changes are their own revision: `uv run python scripts/build_eval_corpus.py`
(and `--check` in CI to catch accidental drift), then regenerate the baseline.
Adding a case means a *real* query with a recorded origin, a rationale, and the
anchor that justifies it — `eval/cases.json` is validated on every run, and a
case without provenance or rationale is refused.

## Known limits

- 15 cases over one documentation corpus: enough to detect a ranking change,
  far too few to claim generality. Do not quote these numbers as a product
  benchmark.
- Document-level judgement only: it does not measure whether the *chunk* handed
  to an agent is the useful one.
- The corpus is documentation, not code. Code retrieval, and the GitHub
  issue/PR text the roadmap promises later, need their own pinned corpus and
  their own judgements.
- Regression tolerance defaults to `0.0`: with 15 cases a single case moving is a
  visible metric move, and one baseline run cannot yet separate signal from
  noise. Set a tolerance from observed run-to-run variance once there is more
  than one measurement, not from a percentage that sounds rigorous.
