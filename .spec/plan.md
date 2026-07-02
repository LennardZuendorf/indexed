---
type: plan
scope: roadmap
updated: 2026-06-29
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
| 11 | Architecture audit remediation | graph fixed, CLI/MCP parity, hygiene, import-graph CI | ◻ IN PROGRESS | `.spec/features/architecture-audit/` |

**Feature 10 detail:** items #1 (ConfigService split), #2 (MCP decompose), #4
(flag parsing), #5 (exception hierarchy), #6 (schema versioning), #7 (public API)
all shipped. Architectural rules promoted to [tech.md](tech.md) § Architectural Rules.
Only the thin-command pattern (extract `knowledge/services/`, shrink oversized
command files) remains open — tracked as [issue #119](https://github.com/LennardZuendorf/indexed/issues/119), not a spec backlog item.

**Feature 11 detail:** Full monorepo audit (2026-06-29) captured in
[features/architecture-audit/](features/architecture-audit/) — requirements
(R1–R11), target architecture, 12 implementation units, six research clusters.
Gate: Phase 0 graph fixes + import-graph CI green; unblocks v2 core/connectors rewrite.

---

## Current Focus

**Architecture audit remediation** — implement
[features/architecture-audit/plan.md](features/architecture-audit/plan.md) units
`architecture-audit/1`–`/12` (protocols package, drop core→connectors, app bootstrap,
CLI/MCP storage parity, config/retry hygiene, dead-code removal). v2 core/connectors
rewrite follows after Feature 11 gate; scope as a separate feature when remediation lands.

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

### 2026-06-29: Architecture audit feature spec
**Decision:** Capture the 2026-06-29 monorepo audit in
`.spec/features/architecture-audit/` (product, tech, plan, six research clusters).
Feature 11 gates v2 rewrite on graph fixes and import-graph CI.
**Rationale:** Audit findings are actionable but too large for root specs; feature
layer holds remediation requirements and phased units without polluting root backlog.

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
