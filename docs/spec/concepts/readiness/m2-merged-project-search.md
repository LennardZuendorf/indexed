---
type: concept
updated: 2026-11-23
---

# Merged Project Search (M2)

[GitHub milestone 12](https://github.com/LennardZuendorf/indexed/milestone/12) · [Parent issue #340](https://github.com/LennardZuendorf/indexed/issues/340) · [Readiness](README.md)

A developer can ask one question across GitHub issues, a local Markdown wiki and code. Results explain where the evidence came from and remain useful for both exact identifiers and broader questions.

| Requirement | Observable behavior |
| --- | --- |
| Unified ranking | One scoped result list can combine relevant records from all three source types. Query and result controls have equivalent meaning through CLI and MCP. Equivalent duplicates do not crowd out relevant hits, and the result preserves independently attributable source references. |
| Verifiable results | Each hit identifies its source and provides the best supported location for citation. A selected hit can expand to bounded nearby evidence while preserving the distinction between the match and added context. |
| Honest outcomes | A healthy zero-match search, partial source failure and total failure produce distinguishable outcomes. GitHub discussion omissions caused by connector limits are visible. A stale expansion reference reports staleness or a missing target. |
| Measured ranking | Compare dense, dense with reranking, hybrid and hybrid with reranking against the strongest existing baseline. Choose the default using the agreed results and document its tradeoffs. |

**Acceptance.** Recover the issue, policy page and implementation in the shared workflow, and prove CLI/MCP parity for search and expansion. Test a failed source alongside healthy sources and a query with no matching evidence. Freeze held-out judgments and quality/latency gates before comparison. Publish per-source and combined ranking quality, exact-identifier and semantic results, distractors on unanswerable queries, latency and the winning configuration.

Ranking budgets, fusion policy and the public expansion surface belong to the feature design.

Issues: [#204 evaluation](https://github.com/LennardZuendorf/indexed/issues/204) · [#205 hybrid search](https://github.com/LennardZuendorf/indexed/issues/205) · [#219 expansion](https://github.com/LennardZuendorf/indexed/issues/219) · [#108 inspect](https://github.com/LennardZuendorf/indexed/issues/108) · [#109 search output](https://github.com/LennardZuendorf/indexed/issues/109) · [#125 error integrity](https://github.com/LennardZuendorf/indexed/issues/125) · [#356 discussion coverage](https://github.com/LennardZuendorf/indexed/issues/356).
