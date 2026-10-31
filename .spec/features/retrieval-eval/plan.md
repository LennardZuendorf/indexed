---
type: feature-plan
feature: retrieval-eval
sibling: tech.md
parent: ../../plan.md
updated: 2026-10-31
---

# Retrieval Evaluation Baseline — Delivery Plan

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)
**Runbook:** [../../../eval/README.md](../../../eval/README.md)

Local measurement implementation is under review in PR #265. Commit/push
approval remains separate from local verification.

### retrieval-eval/1 — Pinned source evidence

Sixteen flat documents include native code, documentation and sanitized issue/PR
snapshots. Twenty-three judged cases include exact and paraphrased probes,
multiple relevant sources, distractors and unanswerable queries.
Git and transformed snapshot provenance remain distinct.

### retrieval-eval/2 — Deterministic metrics and trusted inputs

Validate artifact identity/shape and all indexed bytes before building.
Calculate metrics from saved rankings. Keep missing/corrupt collections and
malformed result envelopes outside scored denominators.

### retrieval-eval/3 — Measured dense and reranked reports

Pin effective model/search settings, scope config overrides and record model
cache snapshots plus numerical environment. Measure identical cases with both
modes. A changed configuration remains a separate experiment.

### retrieval-eval/4 — Comparison and CLI

Validate per-query identity, judgments, derived values, counts and failures.
Refuse missing baseline IDs and malformed input with exit 2. Preserve genuine
regression exit 1 and candidate-only error reporting.

### retrieval-eval/5 — Local and CI verification

Use model-free unit and filesystem integration markers explicitly.
Use one explicit cache for real-model checks and loads. Gate exact reproduction
on numerical environment identity. Keep informative artifacts after test failure.
Run independent reviews and fresh full-suite/lint/type/import/size checks.

## Requirements Trace

| Requirement | Units |
|---|---|
| R1 | retrieval-eval/1 |
| R2 | retrieval-eval/2 |
| R3 | retrieval-eval/3 |
| R4 | retrieval-eval/2 |
| R5 | retrieval-eval/4 |
| R6 | retrieval-eval/5 |

## Follow-ups

Public documentation changes in `indexed-web` remain paired work; this repository
alone does not close all of #204. Website deployment is a separate outcome.
A hard regression gate requires observed variance and a pinned numerical
environment. Chunk-level sufficiency belongs with #219. Hybrid #205 can consume
the existing runner/case contract when implemented.
