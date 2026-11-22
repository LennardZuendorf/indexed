---
type: decision
updated: 2026-11-22
---

# 2026-07-11: CI benchmarking moved to external action

**Decision:** Drop the local `.benchmarks/benchmark_baseline.py` /
`benchmark_compare.py` scripts; run CI benchmarks via the third-party composite
action `lennardzuendorf/pytest-bench-action@v0.0.1` in
`.github/workflows/python-benchmark.yml`. See [CI Benchmarking](../tech/ci-benchmarking/ci-benchmarking.md).
**Rationale:** Baseline capture + comparison logic is generic CI tooling, not
product code — maintaining it in-repo duplicated an already-published action
by the same author. Not tracked as a Feature Sequence row: it's CI
infrastructure, not shipped product surface.
