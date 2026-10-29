---
type: feature-product
feature: retrieval-eval
sibling: tech.md
parent: ../../product.md
updated: 2026-10-29
---

# Feature: Retrieval Evaluation Baseline — Product

Gives retrieval changes a number. Before this feature every ranking change —
reranking, hybrid BM25+vector fusion, chunking, graph scoring — shipped on
"feels better"; after it, each one is compared against a committed baseline of
hit-rate@k and MRR measured on a pinned corpus and a pinned set of judged
queries.

Resolves [issue #204](https://github.com/LennardZuendorf/indexed/issues/204)
(first delivery: pinned corpus + case set + harness + measured baseline).
Consumed by [issue #205](https://github.com/LennardZuendorf/indexed/issues/205).

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)
**Runbook:** [../../../eval/README.md](../../../eval/README.md)

---

## Scope

In:

- A pinned documentation corpus (11 documents, hashed) and a pinned case set
  (15 queries: 11 answerable, 4 deliberately unanswerable), both committed with
  provenance.
- A harness that reports hit-rate@k, MRR, per-query rankings, elapsed time and
  the retrieval configuration alongside the numbers.
- A committed baseline plus a comparison command that returns a verdict
  (improved / regressed / unchanged / incomparable).
- One command to reproduce, one to compare — both offline, no keys, no network.

Out (explicitly):

- LLM judges, faithfulness/relevancy scoring, generated-answer quality.
- Any claim about arbitrary corpora or about code retrieval: the corpus is the
  project's own documentation.
- A hard CI gate on the first delivery. The regression tolerance is chosen from
  observed variance later, not invented now.
- Changing the CLI/MCP result envelope. The harness reads the retrieval contract;
  the presentation shape is #109's call.

## Outcome

A retrieval PR can state, in its body, "hit@5 0.818 → 0.886, MRR 0.578 → 0.712,
no case regressed" — and a reviewer can reproduce it with one command.

## First measured baseline

Corpus tree `134309132376…`, model `sentence-transformers/all-MiniLM-L6-v2`,
v2 dense, rerank off, `k=5`, `max_docs=10`:

- **hit@5 = 0.818** (9 of 11 answerable cases), **MRR = 0.578**
- both misses rank just outside the cut (rank 6 and rank 9), and both are
  questions answered by a roadmap/decision document that shares vocabulary with
  the technical reference docs — the case hybrid retrieval (#205) exists for
- the four unanswerable cases all return a full top-5 of near-miss documents
  (`distractor_leak` 4/4): dense retrieval never says "nothing here"

## Non-goals that look like goals

- Not a product benchmark to publish as "indexed scores X". Fifteen cases over
  one corpus detect movement; they do not measure generality.
- Not a determinism claim about every environment: it claims reproducibility on
  the same model + corpus, and records enough configuration to tell the
  difference when it breaks.
