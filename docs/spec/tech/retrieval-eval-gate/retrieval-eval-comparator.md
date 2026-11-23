---
type: tech
updated: 2026-11-22
applies: [.github/workflows/python-eval.yml, scripts/eval_ab_run.py, "eval/**", "src/indexed/eval/**"]
---

# Retrieval evaluation gate: comparator

One comparator validates complete saved reports with
`indexed.eval.report_validation.report_problems` before metrics or fingerprints.
Both sides require every selected metric, identical query identities/judgments,
full effective model/score configuration, selected model snapshots, complete
CPU/system/Python identities and matching common instrumentation. Invalid
containers, missing evidence, nonfinite/unrepresentable numbers and invalid
tolerance exit 2 with an invalid-result JSON and no verdict. Regressions exit 1;
valid within-policy measurements exit 0. The publisher consumes this sole verdict.

The retained policy is **0.04 absolute points** for hit-rate@k and MRR.
Distractor leakage remains report-only. Historical CI measured 0.0307 MRR
movement at the two-environment boundary; that observation did not diagnose its
cause. A later controlled local experiment isolated generated absolute path
prefixes: changing only 77 inputs moved one relevant rank 5 to 6. Canonical
context fixes that demonstrated harness cause without a product retrieval
change or wider tolerance. Bounded local same-source validation is separate
from hosted acceptance and is not a universal determinism guarantee.

The committed `eval/baseline.json` remains a historical drift reference, with
its original physical-path context. Exact reproduction requires the same input
policy and numerical environment. CI compares its two fresh reports instead.
Machine-block adoption for legacy reports still requires matching the actual
job platform and never overwrites an explicit recorded machine block.

Both reports and `eval-ab.json` are uploaded. A failed harness blocks
measurement; the publisher still displays unavailable phases and preserves
failures. The publisher step alone is advisory. Fork/manual runs retain summary
and artifacts. Dispatch `variance_repeats` accepts integers 1 through 10.
