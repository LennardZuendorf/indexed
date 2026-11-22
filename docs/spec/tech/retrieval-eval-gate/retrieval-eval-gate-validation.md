---
type: tech
updated: 2026-11-22
applies: [scripts/eval_ab_run.py, "src/indexed/eval/**"]
---

# Retrieval evaluation gate: identity validation

Gate identity validation requires a present model's nonempty selected snapshot
and weights. Active reranking also requires its model name and valid cache;
an absent inactive reranker remains compatible. Common instrumentation, when
present, must include a full revision, matching effective normalization policy,
and exactly two valid SHA256 digests for launcher and canonical helper.
CI passes `--require-common-harness`; ordinary local/legacy reports may omit
that instrumentation. Errored queries invalidate the gate rather than reducing
its metric denominators.

Measurement setup/base/head/repeat failures exit 2 through the shared error
trap. They do not synthesize a verdict artifact: the publisher shows the failed
measurement phase and unavailable verdict. Comparator input-read, host-adoption
and report-validation failures write an explicit invalid-result artifact.


The publisher validates comparator-invalid artifacts separately from pass/fail
artifacts. Early failures may contain label-only sides and null tolerance;
unknown identity fields render as unavailable, while escaped reasons retain the
invalid status. Pass/fail still requires complete machine/interpreter sides.
Invalid reasons are limited to ten displayed entries with bounded text and an
artifact link for omitted content; invalid artifacts show no gating table.
