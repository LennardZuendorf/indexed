---
type: plan
scope: roadmap
updated: 2026-07-12
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
| 1 | Core indexing pipeline | read→convert→chunk→embed→index→persist works E2E | ✅ DONE | `src/indexed/core/v1/` |
| 2 | FAISS semantic search | L2 search + score mapping | ✅ DONE | `src/indexed/core/v1/engine/indexes/indexers/faiss_indexer.py` |
| 3 | Jira connectors (Cloud + Server/DC) | JQL-filtered indexing | ✅ DONE | `src/indexed/connectors/jira/` |
| 4 | Confluence connectors (Cloud + Server/DC) | CQL-filtered indexing | ✅ DONE | `.../connectors/confluence/` |
| 5 | File system connector | local files + parsing module | ✅ DONE | `.../connectors/files/`, `src/indexed/parsing/` |
| 6 | Outline Wiki connector | Cloud + self-hosted parity, attachments/OCR | ✅ DONE | `.../connectors/outline/`, tests `tests/unit/indexed_connectors/outline/` |
| 7 | MCP server (stdio/HTTP/SSE) | tools + resources exposed | ✅ DONE | `src/indexed/mcp/` |
| 8 | CLI commands | create/search/update/inspect/remove | ✅ DONE | `src/indexed/cli/knowledge/commands/` |
| 9 | Config & .env loading | single-source resolution, .env hierarchy, .gitignore guard | ✅ DONE | `src/indexed/config/`, [tech-config.md](tech-config.md) |
| 10 | Architecture cleanup (pre-v2) | structural fixes on surviving infra | ◑ MOSTLY DONE | tech.md § Architectural Rules; see below |
| 11 | Architecture audit remediation | graph fixed, CLI/MCP parity, hygiene, import-graph CI | ✅ DONE | `src/indexed/protocols/`; wiring since folded into `src/indexed/cli/composition.py` (Feature 13) and the graph checker into `scripts/check_imports.py` (Feature 14) |
| 12 | Critical bugs (non-core) | #123/#124 security + #114/#110 UX fixed, all gates green | ✅ DONE | `connectors/_url_guard.py`, `commands/create.py`, `commands/search.py` |
| 13 | Foundation (architecture & correctness) | every audited bug fixed behind a characterization harness; typed contracts + core-swap facade; read-mostly config; honest CLI/MCP failures — R1–R7 green | ✅ DONE | `protocols/models.py`, `core/v1/engine/__init__.py` (facade), `src/indexed/cli/composition.py`, connector `from_manifest` |
| 14 | Simplify (codebase reduction) | single package; dead code deleted; CLI/config chrome + process apparatus shrunk — R1,R3,R4,R5 green, R2 partial (indexer deferred) | ✅ DONE | `src/indexed/` (one package, one wheel `indexed-sh`); `scripts/check_imports.py` + `scripts/check_sizes.py` |
| 15 | Review remediation (PR #155) | every confirmed PR #155 review defect fixed behind a regression test — R1–R15 green | ◻ ACTIVE | [features/review-remediation/](features/review-remediation/plan.md) |

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

**Feature 14 Simplify is DONE** (2026-07-10): the seven-package workspace is
collapsed to a single `indexed` package (one wheel `indexed-sh`); dead code + chrome
tests are removed; the CLI/config chrome is shrunk (config CLI 2061→47 over
get/set/list/validate, `create` de-cloned to one schema-driven handler, every command
file ≤300); the process apparatus is unvendored (one root `AGENTS.md` ≤100 lines,
skills install from `skills-lock.json`); and the two deferred Foundation config
cleanups (cached `get_config()/reload()`, single path/mode resolver) landed. Full
suite + system tests green; coverage ≥85% on core/connectors/config; size + import
gates enforced by `scripts/check_sizes.py` + `scripts/check_imports.py`.

**Active: Feature 15 Review Remediation.** The extra-high-effort code review of
PR #155 (14 finders + 8 adversarial verifiers + gap sweep) confirmed a set of
defects the architecture cleanup introduced or left latent — three P1
crashes/data-loss on common paths (config `set` truncating the untargeted
`config.toml`; `indexed-mcp run` crashing on a malformed config; fresh-install
`inspect`/`search` erroring instead of reporting empty), three P1
silent-wrong/crash connector+cache defects (Confluence `CancelledError`, Jira
`enhanced_jql` None, document-cache key omitting parse settings), a systemic
Rich-markup crash on ordinary input (`search "list[int]"`), plus a P2/P3 tail.
Captured as [features/review-remediation/](features/review-remediation/plan.md),
nine mostly-independent units ordered by blast radius, each a green commit with a
regression test. To be worked in the cloud.

The **v2 core/connectors rewrite** remains the next horizon after remediation — it
swaps a module behind the `core.v1.engine` facade over the same on-disk format, now
unblocked (typed contracts + facade + one package + behavior-only suite make it a
drop-in).

**Non-gating deferral (Feature 14):** the indexer factory/registry + multi-indexer
plumbing were NOT deleted — the audit's "phantom generality" premise was wrong
post-Foundation: they are the live embedding-model resolver (3 models) bound to the
on-disk `manifest.indexers[]` byte-stable contract; deleting them would inline
duplicated construction at four call sites and risk collection-load compatibility.
Left as a documented follow-up for the v2 rewrite (see Decision Log 2026-07-10).

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

### 2026-07-12: Feature 15 (Review Remediation) opened
**Decision:** Capture the confirmed defects from the extra-high-effort review of
PR #155 as Feature 15 rather than fixing ad-hoc. The review ran 14 finder passes
(Opus/Sonnet/Haiku subagents) + 8 adversarial verifiers + a gap sweep over the
changed `src/indexed/` surface; every requirement traces to a defect confirmed or
plausible against real code at HEAD (several with live repros). Fifteen
requirements grouped into nine mostly-independent units, ordered P1 (data-loss /
common-path crash / silent-wrong) → P2 → P3 (diagnosability + test coverage).
**Rationale:** the defects are point fixes on stable surface, but each needs a
regression test so the next refactor can't reintroduce it — that is feature-layer
work, not a root backlog. Two altitude questions are deferred to design-in-unit:
whether R7 (Rich-markup safety) lands as a shared render seam vs per-site escaping,
and whether R13 re-wires `max_skipped_items_in_row` skip/retry or deletes the dead
param. Folder deletes before the branch merges per spec rules; any cross-cutting
outcome (R7 seam) promotes to root tech.md at wrap-up.

### 2026-07-11: CI benchmarking moved to external action
**Decision:** Drop the local `.benchmarks/benchmark_baseline.py` /
`benchmark_compare.py` scripts; run CI benchmarks via the third-party composite
action `lennardzuendorf/pytest-bench-action@v0.0.1` in
`.github/workflows/python-benchmark.yml`. See [tech.md](tech.md) § CI Benchmarking.
**Rationale:** Baseline capture + comparison logic is generic CI tooling, not
product code — maintaining it in-repo duplicated an already-published action
by the same author. Not tracked as a Feature Sequence row: it's CI
infrastructure, not shipped product surface.

### 2026-07-10: Feature 14 (Simplify) complete
**Decision:** Shipped Feature 14 across six units, each a green commit: simplify/1
(unvendor `.agents/` skills, one root `AGENTS.md` ≤100 lines, benchmark CI
on-demand); simplify/2 (delete zero-consumer symbols — `SearchArgs`,
`CONFIG_REGISTRY`/`get_config_class`/`list_connector_types`, dead indexer orphans,
the never-instantiated sync Confluence reader, the dead `ProgressUpdate`/
`ProgressCallback` system, the never-batching `indexing_batch_size` loop, the
`_UpdatingCollectionCreator` wrapper); simplify/3 (collapse the 7-package workspace
to one `indexed` package under `src/indexed/` in one history-preserving `git mv` +
mechanical import rewrite, drop `una` + 8 per-package `pyproject.toml` +
`sync_version` role, replace the graph checker with `scripts/check_imports.py`);
simplify/4 (config CLI 2061→47 over get/set/list/validate, `create` de-cloned to one
schema-driven handler, delete `migration.py`, thin commands so every command file
≤300, prune unrendered Rich components, lazy connector-registry, + the two deferred
Foundation config cleanups: `ConfigService.instance()`→cached `get_config()/reload()`
and the single path/mode resolver); simplify/5 (prune pure Rich-chrome tests, rescope
coverage to core/connectors/config/parsing/utils/protocols with cli/mcp exempt,
≥85%); simplify/6 (`scripts/check_sizes.py` size gate + promote the architectural
merge-block to root `tech.md` + reconcile all root specs to the single-package
layout). A 5-finder adversarial bug-hunt over the refactors caught **one real
regression** — `config get --simple-output` on a section/ancestor path leaked nested
secrets in cleartext (masking checked only the queried key, not the returned value) —
fixed with recursive `_mask_sensitive_raw` + a regression test. R1/R3/R4/R5 green;
full suite + system + characterization green; mypy 0-new; validate.sh clean.
**Deferred (R2 partial):** the indexer factory/registry + multi-indexer plumbing were
NOT deleted. The audit's "phantom generality" premise was factually wrong
post-Foundation — `get_indexer_config`/`indexer_factory` are the live path that
resolves the embedding **model** (3 supported models) from the persisted indexer
name, and the `manifest.indexers[]` array is a Foundation byte-stable on-disk
compatibility contract. Deleting the factory would inline duplicated FaissIndexer+
embedder construction at four call sites (an anti-simplification) and risk breaking
existing collections; the multi-indexer flatten only touches an in-memory 1-element
list for near-zero value. Left as a v2-rewrite follow-up.
**Rationale / honesty on size:** the spec's aspirational "~66k→15k / ~6k src / ~8k
tests" targets were **not** met (measured: ~21k src, ~28k tests) and are not
reachable under this feature's own non-goals ("no v2 rewrite, no behavior/feature
removal") — the app/connector/config layers are real functionality, and much of the
CLI shrink was extraction/reorganization (better structure, not raw deletion). The
genuine, durable wins are structural: one package instead of seven, ~12.6k LOC of
vendored skills unvendored, dead code gone, a 97%-smaller config CLI, a de-cloned
`create`, a cleaner config API, and a behavior-only suite with a scoped coverage
gate. `check_sizes.py` guards the real measured baseline (src ≤23k, tests ≤29k) to
prevent regrowth rather than assert a number a rewrite would be needed to hit.

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
regression-guarded by `tests/characterization/`. Size inventory: the 2026-07-06
audit (shipped with Feature 14, retained in git history).
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
