# Retrieval evaluation baseline

The harness measures document retrieval on a small pinned local corpus.
It does not evaluate generated answers or prove general benchmark quality.
Public website documentation remains a paired `indexed-web` follow-up to #204.

## Inputs and artifacts

| Path | Purpose |
|---|---|
| `eval/corpus/` | 16 flat files: 11 documentation snapshots, three native Python files, and two sanitized issue/PR extracts. |
| `eval/corpus.json` | Corpus identity, per-file hashes, tree hash, and source provenance. |
| `eval/sources/` | Authored sanitized GitHub extracts and their capture metadata/hashes. |
| `eval/cases.json` | 23 judged probes: 19 answerable and four deliberately unanswerable. |
| `eval/baseline.json` | Measured dense report. |
| `eval/rerank-baseline.json` | Measured dense-plus-rerank report over identical cases. |
| `eval/experiment.json` | Report hashes, configuration differences and per-case rank movement between modes. |

Code and documentation bytes come from `git show <source_repo_rev>:<source>`.
The revision identifies the bytes actually read; it does not describe an
uncommitted working-tree copy. Sanitized GitHub extracts are separate local
snapshot inputs. Their entries record upstream URL, captured revision/time,
sanitization notes, input path and hash. They do not claim that transformed
text existed at the repository revision.

Per-file hashes and the sorted tree hash bind the corpus bytes.
The runner refuses extra files, directories, symlinks, ambiguous paths,
invalid artifact shapes, and mismatched corpus IDs before building.

`scripts/build_eval_corpus.py --check` verifies the pinned copies without
writing. Source edits, renames and deletion at a valid newer Git revision
are informational; corruption or missing pinned bytes fail. An invalid
`--rev` always fails. Rebuild deliberately with:

```bash
uv run python scripts/build_eval_corpus.py --rev <full-git-revision>
```

## Judgments and metric definitions

The original 15 probes use public issue titles. Eight authored probes add
exact symbols, config keys, error identifiers, issue/PR numbers,
paraphrased implementation intent and rationale. Cases name relevant files,
similar distractors, provenance, rationale and `answered_by` anchors.

Anchor tests resolve `file:line`, `file:first-last` and comma-separated
references against the pinned files. They check document membership, line
range and nonblank endpoints. They do not determine whether the prose or
code supports the judgment. Review that relevance manually whenever fixtures
or judgments change. Freeze judgments before measuring.

- Document ranking keeps the first occurrence of each canonical file name.
  Ties preserve the engine's order.
- Hit-rate@k is the fraction of scored answerable cases with any relevant
  document in the first k results. Empty rankings count as misses.
- Reciprocal rank is 1 divided by the first relevant document's rank, or zero
  for a miss. MRR averages it over scored answerable cases; it is not cut at k.
- Unanswerable cases are outside those denominators. Distractor leakage counts
  unanswerable cases with a labeled distractor inside the first k results.
- Collection load errors and malformed retrieval envelopes are trusted-context
  failures. They are recorded separately and excluded from the denominators.
  A report containing them cannot become a baseline.

Saved query identities, judgments, ranks, arithmetic, counts and failure
summaries must agree before comparison. A report cannot improve by dropping
a query or changing only a headline metric.

## Provision once, measure offline

The default metric/unit path needs no model, network or credentials:

```bash
uv run pytest tests/unit/indexed/eval -m unit -q
```

Provision the embedding model with `indexed init`. Provisioning is the
networked step; measurement uses the resulting local cache. Reranking also
needs `cross-encoder/ms-marco-MiniLM-L-6-v2` locally. For example:

```bash
uv run indexed init --model sentence-transformers/all-MiniLM-L6-v2
uv run python -c 'from huggingface_hub import snapshot_download; snapshot_download("cross-encoder/ms-marco-MiniLM-L-6-v2", allow_patterns=["config.json", "model.safetensors", "pytorch_model.bin", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "vocab.txt"])'
```

Set `HF_HUB_CACHE` explicitly when using a separate cache.
Use that same cache for availability checks and actual loads. Real-model tests
capture the intended cache before pytest isolates HOME.

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 uv run indexed-eval run --out /tmp/eval-dense.json
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 uv run indexed-eval run --rerank --out /tmp/eval-rerank.json
uv run indexed-eval compare --report /tmp/eval-dense.json
uv run indexed-eval compare --baseline eval/rerank-baseline.json --report /tmp/eval-rerank.json
```

Reports record the corpus/case hashes, effective embedding/search/reranker
settings, model cache snapshots, Python/platform, dependency versions and code
provenance. Inspect these fields before attributing movement to ranking code.

A same-environment baseline test always checks corpus, case and configuration
identity. Exact numeric/rank assertions apply only to matching numerical
environments. Different CPUs, Python/library builds or model snapshots can
change retrieval floats even when metric arithmetic is deterministic.

## Comparing and changing evidence

`compare` returns 0 for unchanged/improved, 1 for regressed, and 2 for invalid
or incomparable reports. Corpus, judgment or configuration changes are different
experiments. Tolerance must be finite and nonnegative.

A per-case rank drop, newly failed case, aggregate metric drop, or increased
unanswerable leakage counts as regression. A compensating improvement cannot
hide a regressed case. Recomputing metrics at a different k also recomputes
leakage at that cut.

Dense versus reranked reports intentionally differ in configuration.
Present their side-by-side metrics and per-case movement as an experiment;
ordinary comparison must keep returning incomparable across configurations.

The recorded arm64/Python 3.13.11 experiment measured:

| Mode | hit@5 | MRR | Unanswerable distractor leaks | Errors |
|---|---:|---:|---:|---:|
| Dense | 1.000000 | 0.808772 | 4/4 | 0 |
| Dense + rerank | 1.000000 | 0.828947 | 3/4 | 0 |

Both use corpus `8a52afa74226…` and case set `924efe7313ff…`.
The full hashes and eight per-case rank movements are in
[`experiment.json`](experiment.json). Some cases move down despite the higher
average MRR. This small experiment sets no tolerance or general superiority
claim. Both reports record the dirty working tree and exact source fingerprint
measured before the commit gate. Saved metrics recompute identically in both modes.

Update fixtures or judgments first, review anchors and labels, then regenerate
both reports. Inspect failures and repeat metrics from the saved rankings.
`--write-baseline` writes a local artifact; it does not create a Git commit.
It refuses failures and unverified corpus drift. Commit and push only through
the repository's human gates.

## CI and limits

`python-eval.yml` verifies the pinned corpus, runs harness tests, measures and
compares, then uploads `retrieval-eval` artifacts. The informative measurement
still runs after a harness-test failure when corpus verification succeeded;
the failed test remains visible. Artifact upload runs even after failure.

After artifact upload, a Node 24 publisher writes the job summary and updates
one bot comment on same-repository pull requests. The report shows baseline and
current metrics with deltas, the comparison verdict, per-case rank changes,
environment and configuration differences, and harness or measurement failures.
It links to the workflow run and its artifacts. Missing or invalid report data
is shown as unavailable. A newer PR head prevents an older run from updating
the comment.

Fork pull requests and manual runs retain the job summary and artifacts, with
a notice explaining why no PR comment was posted. Comment publication failures
produce warnings. The publisher uses read-only repository contents and
job-scoped PR comment permission; it does not use `pull_request_target`.

Run the dependency-free publisher tests with Node's built-in test runner:

```bash
uv run node --test .github/scripts/eval-comment.test.cjs
```

Phase one is informative. No hard gate or arbitrary regression tolerance is
inferred from one measurement. Real missing/corrupt-collection tests use the
facade with a local MockEmbedding; mock scores prove failure plumbing, not
retrieval quality.

The corpus remains small, flat and basename-identified. Nested corpora and
duplicate canonical file names are refused. Sanitized GitHub text proves local
fixture retrieval, not live connector behavior. Document-level relevance does
not establish that every returned chunk is sufficient evidence for an agent.
