---
type: tech
updated: 2026-11-22
applies: [.github/workflows/python-benchmark.yml, scripts/benchmark_ab.py, "tests/benchmarks/**"]
---

# CI benchmarking: action configuration

Configured as `cross-branch-tolerance: 1000` on the advisory PR report step
(its failure is continued because that comparison crosses machines), and
`cross-branch-tolerance: 20` on the refresh lane (live: there it is main's drift alarm), the inert
`update-tolerance: 1000`, and a per-test `threshold-map` (max seconds per
benchmark name substring). GitHub Actions has no YAML merge keys, so the two
`with:` blocks are copies of each other; change them together. The
`benchmark-override` label (`override-label`) still waives a *cross-run* report
regression — the A/B gate has no label waiver and always decides from its
validated measurements.

A `concurrency` group (keyed on PR number, else ref; `cancel-in-progress: true`)
prevents overlapping runs from racing each other.

**Known upstream gap:** the action exposes no `update-baseline: false` switch,
which is why this repo scopes write permission instead of switching the path
off. If a release adds one, prefer it over `update-tolerance: 1000` and drop
that value.

Pinned to an exact release tag (`@v1.0.2`), not the floating `@v1` major tag —
the floating tag raced with upstream's own release-automation retagging and
briefly 404'd mid-release (`unable to find version v1`). Bump the pin by hand
on new releases instead.

**Resolved (v1.0.0):** comparability used to key on the runner hostname
(`machine_info.node`), which GitHub-hosted runners randomize per job, so
cross-run comparisons false-positived as regressions. `v1.0.0` gates on a
CPU/system fingerprint instead (`cpu.brand_raw` + arch + core count + `system`),
so `ubuntu-latest` runs on the same CPU model compare cleanly; a genuine
hardware mismatch now skips with `comparison-skipped` (or hard-fails if
`enforce-same-node: "true"`, unset here) instead of hard-failing by default.
Not configured in this repo: `enforce-same-node` (defaults `"false"`; the report
step leaves a cross-run mismatch a warning, because the A/B — not the cross-run
comparison — decides the job).
