---
type: tech
updated: 2026-11-22
applies: [.github/workflows/python-benchmark.yml, scripts/benchmark_ab.py, "tests/benchmarks/**"]
---

# CI Benchmarking

The advisory benchmark maps use 12 s for `batch_parse`, 20 s for
`full_connector_pipeline`, and 30 s for its `_mixed` variant. The mixed key
precedes its substring match. Both jobs use the same map; these caps are
reporting backstops, while the paired A/B comparison owns the PR verdict.

Performance regressions are caught in CI, not via local scripts. The former
`.benchmarks/benchmark_baseline.py` / `benchmark_compare.py` (baseline capture +
diff logic) were deleted and replaced by the GitHub Marketplace action
[`pytest Benchmark Baseline Check`](https://github.com/marketplace/actions/pytest-benchmark-baseline-check)
(`lennardzuendorf/pytest-bench-action`), wired in
`.github/workflows/python-benchmark.yml`, plus one repo-owned comparator,
`scripts/benchmark_ab.py`. A PR run has two halves, and only the first decides
anything.

**The gate: two measurements, one job, one runner.** Before the report action,
`Capture benchmark revisions` pins the event's base SHA, PR head SHA and GitHub
merge-result SHA (`github.sha`). The A/B requires exactly two merge parents,
ending in the captured PR head, and fetches the objects it needs with depth 3 —
the A/B checkout already runs at `fetch-depth: 2`, which brings the merge and
its first parent, so the explicit fetch covers the payload base and the merge
even when those differ. The measured base is the merge commit's **own first
parent** — the commit GitHub built that merge against — never the event
payload's base SHA, which is an earlier snapshot. When the base branch moves
between the webhook snapshot and the merge-ref build, the snapshot lags the
merge and used to fail a valid merge as "provenance invalid": on 2026-11-12 run
`43175675712` carried payload base `dca6be3` while the merge it measured,
`487a1131`, had parents `[600f1f3, 6ff5d2c]`, so the old wrapper proof rejected
a valid merge. The next run on that branch was green because its head,
`930743ae`, merged main and so carried a payload base that matched its merge's
first parent — a different head, not a flake. Measuring the first parent keeps
both sides immutable and keeps the delta exactly the PR's change;
measuring the stale snapshot instead charges the base branch's intervening
commits to the PR. A native-stack wrapper therefore needs no special case — it
is measured as itself. A payload base that differs from the first parent is
reported as a notice, not a failure; missing objects, a merge that does not
have exactly two parents, or a second parent that is not the captured PR head
still fail the measurement.
