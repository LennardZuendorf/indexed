---
type: tech
updated: 2026-11-22
applies: [.github/workflows/python-benchmark.yml, scripts/benchmark_ab.py, "tests/benchmarks/**"]
---

# CI benchmarking: report and baselines

**The report: everything else, advisory.** The pinned action measures
`tests/system` + `tests/benchmarks`, posts its PR comment, and reports drift
against the target branch's committed baseline. The PR invocation has
`continue-on-error: true`: no finite tolerance makes this action observation-only,
since missing names or sufficiently large regressions can still fail it.
`cross-branch-tolerance: 1000` is report policy, not the safety boundary.
The required A/B runs after report failure, independently checks checkout and
Python setup, installs uv, and measures both revisions. Setup failure, failed
pytest or absent result files exits 2. The gate records its exit as a job output
(`pass`, `regression`, `invalid`) and never makes its own job the verdict: a
measured regression reds `Benchmark verdict`, a run that compared nothing reds
`Benchmark verdict: no verdict`, and only one of the two can be red for a given
commit. So a red `Performance Benchmarks` means the job itself broke, never "the
benchmarks were fine but the gate refused to look" (#267, #271). A skipped
comparison is never a pass either: it lands on the no-verdict check with the
reason in the run. The dispatch refresh invocation retains its hard action failure
behavior and live tolerance of 20. Committed baselines remain drift references.

`.benchmarks/baselines/` holds the per-branch JSON baselines (the general
`.benchmarks/*.json` ignore carries a `!baselines/**` exception — negating just
the dir, not `**`, leaves files inside still matched by `*.json` and silently
un-stageable).

**Contract: a PR run measures and gates, it never writes.** The pull_request
job holds `contents: read` and `pull-requests: write` — nothing else. The
action's own update path is still there upstream: when a run drifts past
`update-tolerance`, when the comparison is skipped for a hardware mismatch
(exit 3) or when the base branch has no baseline at all, it stages
`.benchmarks/baselines/main.json` and pushes a `[skip ci]` commit onto the PR
head. With no write scope that push cannot succeed (`continue-on-error` turns
it into a warning), so the PR head is the SHA that was measured — the
untested-head defect of issue #253 cannot recur. `update-tolerance: 1000`
additionally keeps ordinary drift from even staging the commit, for clean logs;
it is not the guarantee, because no tolerance value covers the exit-3 and
no-baseline cases — the read-only token does.
