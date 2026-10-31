---
type: feature-product
feature: retrieval-eval
sibling: tech.md
parent: ../../product.md
updated: 2026-10-30
---

# Feature: Retrieval Evaluation Baseline — Product

Gives retrieval changes a number. Before this feature every ranking change —
reranking, hybrid BM25+vector fusion, chunking, graph scoring — shipped on
"feels better"; after it, each one is compared against a committed baseline of
hit-rate@k and MRR measured on a pinned corpus and a pinned set of judged
queries.

Implements the local measurement scope of
[issue #204](https://github.com/LennardZuendorf/indexed/issues/204).
Public website documentation remains a paired `indexed-web` follow-up.
Consumed by [issue #205](https://github.com/LennardZuendorf/indexed/issues/205).

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)
**Runbook:** [../../../eval/README.md](../../../eval/README.md)

---

## Scope

| Owns | Does not own |
|---|---|
| Local fixture judgments, retrieval metrics, reports and comparisons | Engine ranking algorithms, generated answers, live GitHub verification, website deployment |

In:

- A pinned flat corpus of documentation, native code and sanitized issue/PR
  snapshots, with hashes and source provenance.
- Judged exact symbols, config keys, errors, issue numbers and paraphrased intent,
  including multiple relevant sources, distractors and unanswerable queries.
- A harness that reports hit-rate@k, MRR, per-query rankings, elapsed time and
  the retrieval configuration alongside the numbers.
- A committed baseline plus a comparison command that returns a verdict
  (improved / regressed / unchanged / incomparable).
- One command to reproduce, one to compare — both offline, no keys, no network.
- Measured dense and dense-plus-rerank artifacts with effective configuration
  and model/cache identities. Cross-mode results are a configuration experiment.
- Strict artifact identity/shape validation and missing/corrupt-collection
  evidence. Trusted-context failures never become scored misses.

Out (explicitly):

- LLM judges, faithfulness/relevancy scoring, generated-answer quality.
- Any claim of generality beyond these fixtures or live GitHub connector
  verification from sanitized snapshots.
- A hard CI gate on the first delivery. The regression tolerance is chosen from
  observed variance later, not invented now.
- Changing the CLI/MCP result envelope. The harness reads the retrieval contract;
  the presentation shape is #109's call.

## Outcome

### Requirement: pinned source evidence (R1)

The fixtures MUST pin code, docs and sanitized issue/PR evidence with identity, rationale and
resolvable document references. Include exact probes and paraphrased intent.

#### Scenario: fixture provenance
- **GIVEN** a declared fixture
- **WHEN** it is measured
- **THEN** its bytes and source capture match the manifest and its judgment cites relevant pinned text.

### Requirement: deterministic arithmetic (R2)

The harness MUST compute document hit-rate@k and reciprocal rank from saved rankings. Treat
multiple relevant targets, ties, duplicates, empty results and errors explicitly.

#### Scenario: saved rankings
- **GIVEN** saved rankings
- **WHEN** metrics are recomputed twice
- **THEN** both results match.

### Requirement: measured configuration experiments (R3)

The harness MUST measure identical cases with dense and dense-plus-rerank configurations. Record
both model identities, effective configuration, cache, environment and timing.

#### Scenario: reranking experiment
- **GIVEN** frozen judgments
- **WHEN** both modes run
- **THEN** each report records its applied configuration and cross-mode comparison remains incomparable.

### Requirement: trusted context (R4)

The runner MUST refuse invalid artifacts and corpus identity mismatches before indexing. Record
missing/corrupt collections and malformed results as failures, never misses.

#### Scenario: unavailable collection
- **GIVEN** a missing or corrupt collection
- **WHEN** retrieval runs
- **THEN** a trusted-context failure is recorded outside metric denominators.

### Requirement: honest comparison (R5)

Comparison MUST validate saved evidence and headline arithmetic before comparing. Different
corpora, judgments or configurations are incomparable. Set no invented tolerance.

#### Scenario: missing query
- **GIVEN** a candidate that omits a baseline query
- **WHEN** the reports are compared
- **THEN** the candidate is incomparable instead of improved or unchanged.

### Requirement: reproducible local workflow (R6)

The workflow MUST keep metric tests model-free. Document provisioning and offline real-model runs.
Publish informative CI artifacts and track the separate public-docs pairing.

#### Scenario: failed harness test
- **GIVEN** valid corpus bytes and a failing harness test
- **WHEN** informative CI runs
- **THEN** measurement and artifact publication execute with the failure visible.

A retrieval PR can state, in its body, "hit@5 0.818 → 0.886, MRR 0.578 → 0.712,
no case regressed" — and a reviewer can reproduce it with one command.

## Current measured fixture baseline

The current expanded fixture experiment is recorded in
[../../../eval/experiment.json](../../../eval/experiment.json): dense and
dense-plus-rerank both hit all answerable cases at k=5; MRR is 0.808772 and
0.828947, with four and three unanswerable distractor leaks. These are local
fixture measurements, not a claim of general retrieval quality.

## Initial documentation baseline (historical)

Corpus tree `134309132376…`, model `sentence-transformers/all-MiniLM-L6-v2`,
v2 dense, rerank off, `k=5`, `max_docs=10`:

- **hit@5 = 0.818** (9 of 11 answerable cases), **MRR = 0.578**
- both misses rank just outside the cut (rank 6 and rank 9), and both are
  questions answered by a roadmap/decision document that shares vocabulary with
  the technical reference docs — the case hybrid retrieval (#205) exists for
- three of the four unanswerable cases return a full top-5 of near-miss
  documents (`distractor_leak` 3/4): dense retrieval mostly never says
  "nothing here", and the fourth case is the single piece of evidence that it
  can sometimes rank a near-miss out of the cut

## Non-goals that look like goals

- Not a product benchmark to publish as "indexed scores X". The small fixture
  corpus detects movement; it does not measure generality.
- Not a determinism claim about every environment: it claims reproducibility on
  the same model + corpus, and records enough configuration to tell the
  difference when it breaks.
