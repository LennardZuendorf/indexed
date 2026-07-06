---
type: plan
scope: roadmap
updated: 2026-07-06
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
| 11 | Architecture audit remediation | graph fixed, CLI/MCP parity, hygiene, import-graph CI | ✅ DONE | `packages/indexed-protocols/`, `apps/indexed/.../bootstrap.py`, `runtime.py`, `scripts/check_import_graph.py` |
| 12 | Critical bugs (non-core) | #123/#124 security + #114/#110 UX fixed, all gates green | ✅ DONE | `connectors/_url_guard.py`, `commands/create.py`, `commands/search.py` |
| 13 | Foundation (architecture & correctness) | every audited bug fixed behind a characterization harness; typed contracts + core-swap facade; read-mostly config; honest CLI/MCP failures — R1–R7 green | 📋 PLANNED | [features/foundation/](features/foundation/) |
| 14 | Simplify (codebase reduction) | single package; dead code + mechanism tests deleted; CLI/config chrome + process apparatus shrunk — R1–R5 green | 📋 PLANNED | [features/simplify/](features/simplify/) |

**Feature 10 detail:** items #1 (ConfigService split), #2 (MCP decompose), #4
(flag parsing), #5 (exception hierarchy), #6 (schema versioning), #7 (public API)
all shipped. Architectural rules promoted to [tech.md](tech.md) § Architectural Rules.
Only the thin-command pattern (extract `knowledge/services/`, shrink oversized
command files) remains open — tracked as [issue #119](https://github.com/LennardZuendorf/indexed/issues/119), not a spec backlog item.

**Feature 11 detail:** Shipped 2026-07-03 — `indexed-protocols` leaf package;
core no longer depends on connectors; `bootstrap.py` + `runtime.py` composition
root; `resolve_collections_context()` storage parity for CLI/MCP; explicit config
registration; unified `read_for_mode`; shared HTTP retry policy; dead-code removal;
import-graph CI gate. Unblocks v2 core/connectors rewrite.

---

## Current Focus

**Feature 13: Foundation** then **Feature 14: Simplify** — the 2026-07-06 full
audit (main + app/packages/overengineering passes + a 5-agent correctness hunt)
found ~3k LOC of sound engine carrying ~18k LOC of packaging/wiring/chrome, plus
~33 confirmed behavioral bugs — several corruption/data-loss/secret-leak class
(search silently truncates most content; deletions-only update orphans FAISS
vectors; `config set null` zeroes `config.toml`; secrets written to TOML).

Sequenced deliberately: **Foundation** ([features/foundation/](features/foundation/))
fixes every bug behind a characterization harness (unit foundation/1 — tests
before refactor) and lays the typed-contract + core-swap facade, all in the
current 7-package layout. **Simplify** ([features/simplify/](features/simplify/))
is gated on Foundation DONE and collapses to a single package, deletes dead code
+ mechanism tests, and shrinks CLI/config/process — so deletion happens against
correct, tested, stable contracts. The **v2 core/connectors rewrite** is gated
on both, then swaps a module behind the facade. Issue #119 (thin commands) is
absorbed by simplify/4.

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

### 2026-07-06: Split right-sizing into Foundation + Simplify
**Decision:** After the full audit (main + app/packages/overengineering passes)
and a 5-agent deep correctness hunt that confirmed ~33 behavioral bugs — several
corruption/data-loss/secret class — split the original single right-sizing
feature into two: **Feature 13 Foundation** (architecture & correctness: fix
every bug behind a characterization harness, land typed contracts + core-swap
facade, in the current layout) and **Feature 14 Simplify** (codebase reduction:
collapse to one package, delete dead code + mechanism tests, shrink chrome).
Foundation is gated first; Simplify is gated on Foundation DONE; the v2 rewrite
on both. Per user decision, architecture lands in the current 7-package layout
and the workspace collapse is deferred to Simplify. Tests-before-refactor is
enforced structurally: foundation/1 is the harness that gates every refactor
unit. Evidence + full bug catalogue: [features/foundation/tech-bugfixes.md](features/foundation/tech-bugfixes.md);
size inventory: [features/simplify/research.md](features/simplify/research.md).
**Rationale:** A 3-star personal project doesn't need a 7-package workspace,
1.17× tests-to-source, or 15k LOC of process apparatus; a v2 built on stringly
dict contracts would re-rot. Typed contracts + one facade make the core swap
cheap and safe.

### 2026-07-05: Audit remediation
**Decision:** Cleaned the residue the architecture-audit branch left on Feature 11
infra — collapsed duplicated connector wiring, centralised `missing_wiring_error`
in `indexed_config.errors`, fixed the 2 branch-new `connector_wiring` mypy errors,
deleted the branch-broken `core.v1.Index` facade + dead re-export registries/DTOs,
hardened the import-graph gate to forbid upward `indexed` imports (with a negative
test), de-tautologised weak tests, and corrected the documented mypy command.
**Rationale:** A clean graph deserves clean code/types/tests/docs before the v2
rewrite. Feature spec compounded into [lessons.md](lessons.md) + `AGENTS.md`, then
deleted. 1449 tests green; mypy 0-new on touched files; ruff + validate clean.

### 2026-06-29: Architecture audit feature spec
**Decision:** Capture the 2026-06-29 monorepo audit as Feature 11; remediate via
13 implementation units (protocols package, graph fixes, bootstrap/runtime, CI gate).
**Rationale:** Findings were actionable but too large for root specs; feature layer
held requirements during the branch. **Wrapped up 2026-07-04:** promoted to
[tech.md](tech.md) § Architectural Rules; feature folder deleted — live surface is
code + root specs only.

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
