---
type: tech
updated: 2026-11-22
applies: [.github/workflows/python-benchmark.yml, scripts/benchmark_ab.py, "tests/benchmarks/**"]
---

# CI benchmarking: runner fleet rotation

**Why a committed baseline cannot be the gate (#267, #271).** `ubuntu-latest` is
a heterogeneous fleet. Four jobs of one PR on 2026-10-31 (same code) landed on
`AMD EPYC 7763`, `AMD EPYC 9V74` and `INTEL(R) XEON(R) PLATINUM 8573C`; two PR
runs minutes apart on 2026-11-01 produced opposite verdicts — #252's job passed
against a matching baseline, #268's failed because it landed on a 9V45 and
nothing could be compared. Before #268 that comparison skipped with a warning
and the check was green **while comparing nothing**; after #268 it failed, which
made the lottery visible but left roughly half of all PR runs red for no reason.
Neither state is a verdict, and no tolerance fixes it: three consecutive runs on
the *same* CPU model still disagreed (`test_parse_large_markdown` 690 → 943 ms,
`test_cli_license` 43 → 82 ms, unchanged diff). Only measuring both sides in one
job cancels hardware and tenancy, which is why #268's fail-on-skip guard is
**removed** here rather than kept — it enforced honesty about a comparison that
no longer decides anything. The A/B needs no such guard: a machine mismatch
inside one job is a harness bug and exits 2, and a skipped cross-run comparison
cannot make the gate green because the gate does not read it.

**Fleet rotation is repairable: `accept_cpu_change`.** The refresh lane refuses
a fingerprint change by default, because adopting another machine's numbers
would poison the very reference the gate compares against. `workflow_dispatch`
takes `accept_cpu_change: true`, which lets the refresh proceed, forces the
refresh PR even when the numbers moved less than `DRIFT_PCT`, and records old vs
new fingerprint in the job summary and the refresh PR body. The fingerprint
contains CPU brand, architecture, core count and system. The title marks the
hardware change with `(new CPU)`, including when updating an existing PR. That
PR's table is a
**measurement, not a verdict** — a cross-CPU diff cannot say whether code got
slower — and it exists so the next PR run compares like with like. Without that
input no mechanism in the repo can re-record a rotated baseline. That repair
cannot deadlock on the check it repairs: `.benchmarks/**` is not in this
workflow's `paths` filter, so the baseline-only refresh PR triggers no benchmark
run at all, and the guard (below) is the only check it faces.

**Corpora are pinned, never the repo's own docs.**
`tests/benchmarks/test_parsing_performance.py` measures the parsing pipeline
over a frozen snapshot committed in
`tests/benchmarks/fixtures/parsing_corpus/`, not over `docs/spec/`. Measuring the
live spec tree coupled the gate to the docs: PR #278 added three feature spec
files and `test_full_connector_pipeline_docs` went 9.27 s → 11.79 s (+27.1%,
FAIL) while `test_full_connector_pipeline_mixed`, which builds its own
workspace, moved +4.1% — the corpus had changed, not the code. A corpus is a
fixed input set: its bytes are locked by `parsing_corpus.sha256` and enforced by
`tests/unit/test_benchmark_corpus_pin.py`, and the fixture tree is excluded from
the trailing-whitespace/end-of-file hooks so a hook run cannot silently break
that lock. Refreshing the corpus is a deliberate change that calls for a
baseline refresh afterwards; never point a benchmark at documents the project's
own workflow keeps growing.
