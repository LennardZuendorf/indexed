---
type: plan
scope: roadmap
updated: 2026-07-09
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
| 13 | Foundation (architecture & correctness) | every audited bug fixed behind a characterization harness; typed contracts + core-swap facade; read-mostly config; honest CLI/MCP failures — R1–R7 green | ✅ DONE | `protocols/models.py`, `core/v1/engine/__init__.py` (facade), `apps/indexed/.../composition.py`, connector `from_manifest` |
| 14 | Simplify (codebase reduction) | single package; dead code + mechanism tests deleted; CLI/config chrome + process apparatus shrunk — R1–R5 green | 📋 PLANNED | [features/simplify/](features/simplify/) |

**Feature 10 detail:** items #1 (ConfigService split), #2 (MCP decompose), #4
(flag parsing), #5 (exception hierarchy), #6 (schema versioning), #7 (public API)
all shipped. Architectural rules promoted to [tech.md](tech.md) § Architectural Rules.
Only the thin-command pattern (extract `knowledge/services/`, shrink oversized
command files) remains open — tracked as [issue #119](https://github.com/LennardZuendorf/indexed/issues/119), not a spec backlog item.

**Feature 11 detail:** Shipped 2026-07-03 — `indexed-protocols` leaf package;
core no longer depends on connectors; app composition root (then `bootstrap.py` +
`runtime.py`, folded into `composition.py` by Feature 13);
`resolve_collections_context()` storage parity for CLI/MCP; explicit config
registration; unified `read_for_mode`; shared HTTP retry policy; dead-code removal;
import-graph CI gate. Unblocks v2 core/connectors rewrite.

**Feature 13 detail:** Shipped 2026-07-08 — every audited bug fixed behind the
foundation/1 characterization harness (foundation/2–6); typed data contracts in
the `protocols` leaf (`Manifest`/`ConvertedDocument`/`Chunk`/`CollectionSearchResult`,
byte-stable round-trip) + corrected connector protocols (foundation/7); the
`core.v1.engine` facade (single core surface, v2 swap seam) + one `composition.py`
wiring site with two required callables, connector `from_manifest` replacing the
per-source/`localFiles` branches (foundation/8); read-mostly config verified
byte-stable across updates + both functional-wrapper singletons removed
(foundation/9). Two config tech-refinements are deferred follow-ups (foundation/9
note, shipped in PR #153): the `ConfigService.instance()` → `get_config()/reload()`
rename and the path/mode resolver consolidation — structure-only, R3 does not depend
on them; both are folded into Feature 14 Simplify (simplify/4). Unblocks Feature 14
(Simplify).

---

## Current Focus

**Feature 14: Simplify** — **Feature 13 Foundation is DONE** (2026-07-08): every
audited bug is fixed behind the characterization harness, typed contracts + the
`core.v1.engine` facade + one `composition.py` wiring site are in place, and
config is read-mostly (verified byte-stable). R1–R7 green; full suite green; mypy
at baseline. Two config tech-refinements are deferred follow-ups (foundation/9
note) — structure-only, not gating.

**Simplify** ([features/simplify/](features/simplify/)) is now unblocked: collapse
the seven-package workspace to a single package, delete dead code + mechanism
tests, and shrink CLI/config/process chrome — deletion now happens against
correct, tested, stable contracts. The **v2 core/connectors rewrite** is gated on
both, then swaps a module behind the facade. Issue #119 (thin commands) is
absorbed by simplify/4.

**Deferred config cleanups (from Foundation, non-gating):** the
`ConfigService.instance()` → cached `get_config()/reload()` API rename (~86 call
sites) and the path/mode resolver consolidation (`WorkspaceManager`/
`has_local_config` triplication → one home). Their functional harm was fixed in
Feature 11 / foundation/6d; these are cosmetic/structural and can fold into
Simplify's config work.

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

### 2026-07-09: Retire the Foundation feature spec
**Decision:** Feature 13 Foundation is DONE/merged (PR #153), so its
`.spec/features/foundation/` folder is retired. The still-owed architectural rules
were promoted into root tech specs — typed data contracts and the corrected connector
protocol/`from_manifest` into [tech.md](tech.md) § Protocols Package +
[tech-core.md](tech-core.md) § Typed Data Contracts; the `core.v1.engine` facade +
single `composition.py` wiring site into [tech.md](tech.md) § Core Facade & App
Composition Root (replacing the stale `bootstrap.py`/`runtime.py` description); the
corrected protocol into [tech-connectors.md](tech-connectors.md) § Connector Protocol.
The full 2026-07-06 bug catalogue was **not** re-promoted (all ~40 defects are fixed
and it is resolved backlog — root stays high-level with no backlog); it lives in PR #153
and git history, with behavior regression-guarded by `tests/characterization/`. The
single-`Progress`-protocol rule was deliberately **not** promoted: the dual
callback system still exists and its collapse is a Feature 14 (simplify/2) target, so
promoting it now would be spec-drift ahead of code. **Rationale:** a completed feature
folder must not linger; content that outlives the branch belongs in root specs, and
resolved backlog belongs in history, not the spec.

### 2026-07-08: Foundation (Feature 13) complete; two config cleanups deferred
**Decision:** Shipped foundation/7 (typed contracts in the `protocols` leaf),
foundation/8 (the `core.v1.engine` facade + one `composition.py` wiring site +
connector `from_manifest`, deleting `bootstrap.py`/`runtime.py`/
`connector_wiring.py`), and foundation/9 (read-mostly config verified byte-stable
via `tests/system/test_read_mostly_config.py`; both functional-wrapper singletons
removed). R1–R7 green, full suite green, mypy at baseline, import-graph clean.
**Deferred** the `ConfigService.instance()` → `get_config()/reload()` API rename
(~86 call sites) and the path/mode resolver consolidation to a follow-up (they
can fold into Simplify's config work). **Rationale:** the self-replacing
singleton's only functional harm (dropping registered specs on `reset`) was
already fixed in foundation/6d, so what remains is a cosmetic/structural change
with no behavioral payoff; forcing an 86-site refactor as the last unit of an
unattended run risked destabilizing a green tree for no requirement gain. R3
(config is user-owned) is satisfied and regression-locked without it.

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
unit. Evidence: the full 2026-07-06 bug catalogue (~40 defects, all fixed) shipped in
the Foundation merge (PR #153) and remains in git history; the behavior it locked in is
regression-guarded by `tests/characterization/`. Size inventory:
[features/simplify/research.md](features/simplify/research.md).
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
