---
type: plan
scope: roadmap
updated: 2026-06-23
---

# Development Plan: indexed

Root roadmap. Whole-feature gates only — no unit-level backlog, no long-horizon
wishlist. Current focus + delivered surface.

**For features (what/why), see [product.md](product.md). For architecture, see [tech.md](tech.md).**

---

## Current Status

**v0.1.0 Alpha** — released 2026-02-16. Core pipeline, search, MCP, CLI, config
all shipped. Breaking changes still allowed (alpha).

---

## Feature Sequence

Binary whole-feature gates. A feature is DONE when shipped and its live surface
is the truth. Cross-feature order is a whole-feature gate, never a unit edge.

| # | Feature | Gate | Status | Live surface |
|---|---------|------|--------|--------------|
| 1 | Core indexing pipeline | read→convert→chunk→embed→index→persist works E2E | ✅ DONE | `packages/indexed-core/src/core/v1/` |
| 2 | FAISS semantic search | L2 search + score mapping | ✅ DONE | `core/v1/engine/indexes/faiss_indexer.py` |
| 3 | Jira connectors (Cloud + Server/DC) | JQL-filtered indexing | ✅ DONE | `packages/indexed-connectors/src/connectors/jira/` |
| 4 | Confluence connectors (Cloud + Server/DC) | CQL-filtered indexing | ✅ DONE | `.../connectors/confluence/` |
| 5 | File system connector | local files + parsing module | ✅ DONE | `.../connectors/files/`, `packages/indexed-parsing/` |
| 6 | Outline Wiki connector | Cloud + self-hosted parity, attachments/OCR | ✅ DONE | `.../connectors/outline/`, tests `tests/unit/indexed_connectors/outline/` |
| 7 | MCP server (stdio/HTTP/SSE) | tools + resources exposed | ✅ DONE | `apps/indexed/src/indexed/mcp/` |
| 8 | CLI commands | create/search/update/inspect/remove | ✅ DONE | `apps/indexed/src/indexed/knowledge/commands/` |
| 9 | Config & .env loading | single-source resolution, .env hierarchy, .gitignore guard | ✅ DONE | `packages/indexed-config/`, tech.md § Configuration System |
| 10 | Architecture cleanup (pre-v2) | structural fixes on surviving infra | ◑ MOSTLY DONE | tech.md § Architectural Rules; see below |

**Feature 10 detail:** items #1 (ConfigService split), #2 (MCP decompose), #4
(flag parsing), #5 (exception hierarchy), #6 (schema versioning), #7 (public API)
all shipped. Architectural rules promoted to [tech.md](tech.md) § Architectural Rules.
Only the thin-command pattern (extract `knowledge/services/`, shrink oversized
command files) remains open — tracked as [issue #119](https://github.com/LennardZuendorf/indexed/issues/119), not a spec backlog item.

---

## Current Focus

v2 core/connectors rewrite. The cleanup landed surviving infra (`indexed-config`,
`utils`, CLI, MCP) on a clean foundation; v2 replaces `core/v1` and
`indexed-connectors` against the rules in [tech.md](tech.md) § Architectural Rules.
Scope the v2 work as a feature under `.spec/features/<name>/` when it starts.

---

## Git Developer Features (scoped, not started)

Developer-first git linkage — branch-scoped feature specs under `.spec/features/`.
Whole-feature gates only; cross-feature order below, never unit edges.

| Feature | Gate | Status | Spec |
|---|---|---|---|
| Git metadata enrichment | blame-derived git facts attached to code chunks as sidecar metadata (not embedded), returned in results | ◻ NOT STARTED | [features/git-metadata-enrichment/](features/git-metadata-enrichment/product.md) |
| Branch-aware collections | per-branch index variants + content-hash embedding reuse across branches | ◻ NOT STARTED | [features/branch-aware-collections/](features/branch-aware-collections/product.md) |
| Blame & ownership | ownership in search output + `who_owns` MCP tool + CLI view | ◻ NOT STARTED | [features/blame-ownership/](features/blame-ownership/product.md) |
| Git history documents | commits as a `doc_type: "commit"` in the same collection, cross-linked to code | ◻ NOT STARTED | [features/git-history-documents/](features/git-history-documents/product.md) |

**Sequence (whole-feature gates):**

- **Git metadata enrichment** is the keystone — start first. **Branch-aware collections** is an independent foundation (companion to the planned filewatcher PR); can run in parallel.
- **Blame & ownership** starts when *Git metadata enrichment* is DONE (it surfaces that feature's persisted blame).
- **Git history documents** starts only after the engine can hold heterogeneous documents — tracked as [Merged Collection Graphs (powered by LlamaIndex), #148](https://github.com/LennardZuendorf/indexed/issues/148) — and relies on *Git metadata enrichment* for the code-side cross-link.

**Backlog (GitHub issues, not specs):** git-signal re-ranking
([#144](https://github.com/LennardZuendorf/indexed/issues/144)), diff-scoped search
([#145](https://github.com/LennardZuendorf/indexed/issues/145)), staleness + git-hook
auto-update ([#146](https://github.com/LennardZuendorf/indexed/issues/146)), time-travel
search ([#147](https://github.com/LennardZuendorf/indexed/issues/147)).

---

## Versioning Strategy

`MAJOR.MINOR.PATCH`.

- **MAJOR (0→1):** stable API, production-ready
- **MINOR:** new features, backward compatible
- **PATCH:** bug fixes only

Alpha (current): breaking changes allowed. Beta (v0.5+): API stabilizing.
Stable (v1.0): semver guarantees. Dates are targets, not commitments — quality
over schedule.

---

## Decision Log

### 2026-06-09: Spec cleanup
**Decision:** Migrate `docs/specs/` feature specs into root, promote shipped
feature detail, discard long-horizon roadmap backlog, route remaining cleanup
work to GitHub issues.
**Rationale:** Latest spec rules — feature folders are branch-scoped and deleted
when done; root holds value-prop + architecture + current plan only; no backlog
in specs.

### 2026-02-16: Alpha status
**Decision:** Mark v0.1.0 alpha, breaking changes allowed.
**Rationale:** Need flexibility to iterate on API from feedback.
