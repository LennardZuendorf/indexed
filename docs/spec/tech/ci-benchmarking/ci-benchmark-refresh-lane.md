---
type: tech
updated: 2026-11-22
applies: [.github/workflows/python-benchmark.yml, scripts/benchmark_ab.py, "tests/benchmarks/**"]
---

# CI benchmarking: refresh lane

**Only a baseline-only PR may move main's baseline.** A PR that changes code
must not touch that file: its gate would otherwise compare against numbers the
PR itself wrote, so a regression would land as the new reference instead of
failing. `.github/workflows/baseline-guard.yml` enforces both halves — it fails
a code-changing PR that rewrites the file, and passes a PR whose only change is
a baseline *rewrite*. The door is deliberately not "nothing but that file": a
PR that deletes it also changes nothing else, yet removing main's baseline
disarms the drift monitor (the refresh lane has nothing to compare against and
the PR report prints a first-run notice), so the reference disappears without a
single red check. The guard
therefore requires the file to be present at HEAD before it opens the door, and
fails a deletion with an explicit message. Because the benchmark job can no
longer add a `[skip ci]` commit, the guard's remedy ("restore the file, re-run
the benchmark job") now converges; a re-run cannot re-add it.

**Refresh lane.** `.github/workflows/python-benchmark.yml` is also
`workflow_dispatch`-able, and its `refresh-baseline` job runs only when
dispatched on `main` (that job alone opts into `contents: write` +
`pull-requests: write`). It re-measures through the same pinned action and the
same pin and the same measurement inputs as the PR job's report step; since the
action's update path is
pull_request-only, its "Save baseline" step only rewrites the file in the
workspace. If that differs from `main`'s copy, the job force-pushes it to
`chore/benchmark-baseline-refresh` and opens (or updates) one PR changing
nothing but the baseline. When the repository forbids Actions from opening pull
requests (`GITHUB_TOKEN` cannot, whatever `permissions:` the job grants — the
setting is *Actions → General → Workflow permissions → "Allow GitHub Actions to
create and approve pull requests"*), the push still stands and the handoff fails
loudly instead of dying on GitHub's raw GraphQL error: the step summary names
the pushed branch and commit, carries a paste-ready `gh pr create` line, the
body file's contents (the runner's copy dies with it) and the captured stderr,
and the step annotates `::error::` with that setting and the run URL before
exiting 1. A silent success would leave a pushed baseline nobody knows to
review. A >20% slowdown against `main`'s previous numbers
fails the run before that step — adopt numbers only once a slowdown is
understood as expected. Nothing refreshes on `push` to `main`: one refresh PR
per merge would be noise, so moving the baseline stays a deliberate maintainer
action.
