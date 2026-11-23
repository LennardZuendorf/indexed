---
type: tech
updated: 2026-11-22
applies: [.github/workflows/python-benchmark.yml, scripts/benchmark_ab.py, "tests/benchmarks/**"]
---

# CI benchmarking: A/B comparator

`Same-job A/B gate` measures the merge's first parent and its corresponding PR
merge result back to back. Each has a separate detached worktree and venv
installed from that revision's lock with `uv sync --locked`. Logs and summary
name the actual measured commits as base and merge result, never as a Git merge
base or an unmerged head. The gate requires all three selected rows:
`test_searcher_first_search`, `test_parse_markdown_docs`, and
`test_parse_large_markdown`. Repeatable `--expected-benchmark` arguments pin
that selected set even if pytest omits a test on both sides. Only the common
`tests/` prefix is normalized to match pytest-benchmark fullnames.

`scripts/benchmark_ab.py` requires unique identical row sets, finite positive
selected durations, and complete matching CPU/system and Python identities.
Malformed containers, missing rows/statistics, duplicates, unusable identities,
and nonfinite or negative tolerance exit **2** with
`::error title=Same-job measurement invalid::` and no verdict. The comparator
prints both validated fingerprints. A valid measurement exits **1** only when
a merge-result duration exceeds the captured base by more than `AB_TOLERANCE`
(20 %); otherwise it exits **0**. Zero tolerance is valid.

Two guards keep the benchmark lane from deciding on a comparison that measured
nothing. Each benchmark row must report at least **three rounds** in its own
result file (`MIN_ROUNDS`); a row with one round, a missing round count or a
non-integer one is a refusal naming the row and its count, never a pass —
one round is the runner's mood, not the diff. And every result file must carry
the fixture-set identity the measuring job stamped into it: `measure()` in the
A/B step runs `--stamp-corpus <result> --corpus-root
<worktree>/tests/benchmarks/fixtures`, which hashes every file under that
worktree's frozen corpus by relative path and content. Both sides must agree
on the digest (`benchmark_corpus.sha256`); a differing digest is a corpus
change and therefore a different experiment, and an absent identity is a
refusal, not a pass. Each side digests its own tree, so a PR that edits the
corpus cannot be compared against the base it changed.

The selected statistic defaults to the **minimum** (`--stat` can select another
statistic). Historical unchanged-code measurements found means disagreeing by
up to 20 %, medians by 12 % and minimums by 0.7 %. The earlier #271 subset run
`41407096799` added 40 s to an 8.5-minute report job; that timing predates the
explicit two-worktree setup and is not a fresh performance measurement.
