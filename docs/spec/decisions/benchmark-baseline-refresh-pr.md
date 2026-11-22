---
type: decision
updated: 2026-11-22
---

# 2026-10-27: benchmark PR runs gate only; the baseline moves via a refresh PR (issue #253)

**Decision:** The `pull_request` benchmark job now holds `contents: read` +
`pull-requests: write` and nothing more, so `pytest-bench-action` can no longer
push its `chore(benchmark): update baseline … [skip ci]` commit onto a PR head
(#252 produced four of them, each undone by hand). `update-tolerance: 1000`
keeps ordinary drift from even staging that commit. The baseline moves only
through the new `workflow_dispatch` `refresh-baseline` job, which runs on
`main`, re-measures, and opens one PR changing nothing but
`.benchmarks/baselines/main.json`; `baseline-guard.yml` was narrowed to allow
exactly that shape and still fail a code-changing PR that rewrites the file.
**Rationale:** the untested head was the real damage — `[skip ci]` suppresses
`synchronize`, so the guard could never judge the SHA that carried the move, and
the guard's own remedy could not converge while the action re-created the commit
on every run. Scoping the token is a permission boundary, not a heuristic: the
action's `should_update` path also fires on a hardware-mismatch skip (exit 3)
and on a missing baseline, which no tolerance value can neutralise. The
baseline still has to be refreshable, hence the reviewed refresh PR rather than
a bot push to a branch-protected `main`. See [CI
Benchmarking](../tech/ci-benchmarking/README.md).
