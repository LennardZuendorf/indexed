---
type: plan
scope: roadmap
updated: 2026-09-05
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
| 15 | Review remediation (PR #155) | every confirmed PR #155 review defect fixed behind a regression test — R1–R15 green | ✅ DONE | merged to `main` in PR #155; regression tests in `tests/` (feature folder wrapped up 2026-07-19) |
| 16 | Core v2 (LlamaIndex engine) | v2 engine + v1/v2 coexistence, routing, migration — R1–R13 green | ✅ DONE | `src/indexed/core/v2/`, version-dispatching facade `src/indexed/core/engine.py` + `core/versioning.py`; tests `tests/unit/indexed/core/v2/`; migration `core/v2/migration.py` |
| 17 | Core v2 discoverability (issue #188) | `--engine`/rerank flags surfaced, clean engine error on all 4 surfaces, README + every command's `--help` — R1–R7 green | ✅ DONE | `src/indexed/cli/knowledge/commands/{_create_options,_create_commands,create,_create_helpers,search}.py`, `core/engine.py`, `core/v2/{retrieval,services}`, `config/commands/set.py`, `cli/composition.py`, `README.md`, `cli/knowledge/cli.py` |
| 18 | Core v2 rendering fixes (issue #187) | all 8 PR #162 review polish findings fixed behind regression tests — R1–R8 green | ✅ DONE | `cli/app.py`, `cli/utils/components/{alerts,theme,cards}.py`, `cli/knowledge/commands/{update_service,search_render,_create_options,inspect}.py`, `connectors/files/schema.py`, `core/engine.py` |
| 19 | GitHub Projects/Issues connector | issues+PRs+Projects v2 indexed; incremental update | ◔ IN DESIGN | [features/github-connector/](features/github-connector/) · [#90](https://github.com/LennardZuendorf/indexed/issues/90) |

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

**Feature 16 Core v2 is DONE** (implemented in PR #158 + end-to-end testing
fixes, 2026-07-19): a LlamaIndex-based engine coexisting with the frozen v1
engine behind the version-dispatching `indexed.core.engine` facade, with
manifest-authoritative per-collection routing, explicit engine selection for new
collections, optional reranking, unified cross-engine relevance, and safe v1→v2
migration (dry-run, automatic backup, rollback, purge). Live surface:
`src/indexed/core/v2/`, `core/engine.py`, `core/versioning.py`; tests
`tests/unit/indexed/core/v2/`. Feature 15 (Review Remediation, merged in PR #155)
and Feature 16 both had their feature-spec folders promoted + deleted on
2026-07-19 (v2 routing contract → [tech.md](tech.md) § Core Facade & App
Composition Root; lessons → [lessons.md](lessons.md)). The full v2 planning
artifact (research + ADRs) lives in git history (PR #158).

**Feature 17 Core v2 Discoverability is DONE** (implemented 2026-09-01, spec
drafted 2026-08-30): seven product/UX requirements, five units, clustered
from the PR #162 review in
[issue #188](https://github.com/LennardZuendorf/indexed/issues/188) plus two
same-shape sibling defects folded in — `--engine` surfaced on `index create`
and its four leaf subcommands (plus a group-level `--engine` callback on
`index create` itself, added during final review to fully satisfy R1's
requirement text); a `--rerank`/`--no-rerank` flag on `index search` that
prints a hint rather than silently no-op on a v1-only search (routed to
stderr under `--simple-output` to keep stdout JSON-pure); a clean,
byte-identical single-line engine-error message on all four surfaces that
can catch a bad value (`--engine` flag, env, `config set core.engine`, and
hand-edited `config.toml`); Core v2 mentioned in README's `## Usage`; and
every knowledge command's `--help` (not just `migrate`'s) rendering its own
docstring. No correctness risk; Core v2 itself (Feature 16) already worked —
this was entirely a discoverability/UX surface fix. Implemented via
`superpowers:subagent-driven-development` (one implementer + one task review
per unit, all 5 Approved) plus a final whole-branch review that caught 2 real
cross-unit bugs a per-unit review couldn't (a Rich-markup bug swallowing
`--rerank`'s help text, and the group-level `--engine` gap above), fixed in
one wave and re-verified clean. One newly-discovered 5th engine-error surface
(`config validate`/`list`/`get`) was deliberately left out of scope rather
than expanding past the CONFIRMed plan — recorded as a known follow-up
candidate (see below). Full gate green: ruff/ty/import-graph clean, full
suite 93.30% coverage (>85% required). **Wrapped up 2026-09-02:** the
durable cross-cutting content promoted to root specs — the leaf/group/root
`--engine` precedence + shared-`ctx.obj` mechanism and the four-surface
error normalizer to [tech-app.md](tech-app.md) § Engine Selection; the Rich
markup-swallows-bracketed-help-text gotcha to [tech-app.md](tech-app.md) §
Markup Safety and `AGENTS.md` Learnings; `--engine`/`index migrate`/
reranking as shipped rows in [product.md](product.md) § Features (CLI +
Search — also closed pre-existing drift where Feature 16 had shipped without
a features-table update); resolved backlog (the R1-R7 fix-by-fix detail,
the 5th engine-error surface note, the deferred generic misplaced-option
hint) lives in PR #191 and git history, not the spec. Feature-spec folder
deleted — live surface is code + root specs only.

**Note (supersedes earlier wording):** the v2 rewrite ships behind the *same
facade names* but over a **new version-marked on-disk format** — the "same
on-disk format" drop-in premise was superseded by core-v2 ADR-1 (v2's goals —
pluggable stores, deletes/filters — cannot be expressed in the v1 format;
core-v2 ADR-1, git history / PR #158). The v1 format stays frozen and fully supported.

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

### 2026-09-03: Feature 18 (Core v2 Rendering Fixes, issue #187) shipped
**Decision:** Implemented all 5 units (R1–R8 green) via
`superpowers:subagent-driven-development` — a fresh implementer subagent per
unit, a task-scoped spec+quality review after each (all 5 Approved; Minor
findings deferred to this log), then a final whole-branch review on the most
capable available model. Two integration-level gaps surfaced that no
per-unit review could see, both fixed and re-verified:
1. The controller's own post-unit full-suite run (not any task's scoped
   tests) caught one pre-existing test (`test_from_manifest.py`) asserting
   R3's old, now-superseded behavior (a glob pattern normalized to its
   `fnmatch.translate()` regex form) — outside Task 2's stated file list.
   Fixed by updating the assertion to the new, correct propagation value;
   no other sibling test depended on the old form.
2. The final whole-branch review found 4 Important findings the per-unit
   reviews structurally couldn't reach, fixed in one wave and re-verified
   clean by rendering real output (not just reasoning about it):
   - R1's fix (route `IndexedError` through the existing `print_error` panel)
     introduced a double-escape regression: `print_error`'s `Text(...)` sink
     renders literally, but the call site still `escape()`d first (correct
     for the OLD markup-parsed sink, wrong for the new literal one) — any
     error message containing `[` printed a visible backslash. Fixed by
     dropping the now-incorrect `escape()` call; the same pattern was found
     and fixed in a second, pre-existing (not introduced by this feature)
     call site (`search_render.py`'s `_print_collection_errors`).
   - R2's own written acceptance scenario (a v2 model descriptor on one line
     at 100+ columns) was unmet at ANY terminal width — the 100-column max
     clamp and a pure `ratio`-based label/value column split combined to cap
     below what a realistic descriptor needs. Fixed by raising the max to
     120 and switching the label column to a min-width auto-sizing column
     instead of ratio-based, verified by rendering the actual failing
     descriptor at multiple terminal widths, not by re-deriving the arithmetic.
   - R3's requirement that the new row align with its neighbors was left
     unmet — the `"Included Patterns"` label (17 chars) blew the existing
     10-char label-padding budget the sibling rows use. Fixed by shortening
     to `"Included"` (8 chars, matches the existing `"Excluded"` row).
   - R6's score-labeling requirement ("wherever a score renders") missed one
     of three render paths — `index search --compact` still rendered
     unlabeled scores. Fixed by applying the same `scoreKind` labeling
     pattern Task 4 already used in the other two paths.
**Rationale:** two independent verification layers — the controller's own
full-suite run between units, and a most-capable-model whole-branch review
after all units — exist precisely to catch defects no single unit's scoped
tests or review can see by construction. Both caught real, fixable gaps here;
neither required expanding the CONFIRMed 8-requirement scope. A handful of
Minor findings (stale docstrings describing superseded behavior in
`alerts.py`/`engine.py`; a pre-existing, practically-unreachable markup-escaping
gap in `format_search_results_compact` that the R6 fix extended to also carry
`score_kind`; duplicated score-label lookup logic across three render
functions; a legacy collection with a non-default glob pattern still
displaying raw regex on `update` until re-created) were deliberately left
unfixed rather than silently widening the branch past what two full review
passes had already scoped — recorded here, not fixed ad-hoc. Full gate green
throughout: ruff/ty/import-graph clean, full suite 1934 passed / 1 skipped,
93%+ coverage (>85% required).

### 2026-09-01: Feature 17 (Core v2 Discoverability, issue #188) shipped
**Decision:** Implemented all 5 units (R1–R7 green) via
`superpowers:subagent-driven-development` — a fresh implementer subagent per
unit, a task-scoped spec+quality review after each (all 5 Approved, only
Minor findings deferred to this log), then a final whole-branch review on the
most capable available model to catch what no per-unit review could: cross-unit
interactions. That review found no Critical issues but 3 real Important ones,
fixed in one wave and re-verified clean by a scoped re-review:
1. `--rerank`'s `--help` text contained the literal substring `[core.v2.rerank]`,
   which Rich's markup parser silently swallowed from the rendered output —
   the exact config key the flag's help exists to name was invisible. Fixed
   by dropping the brackets (matching the neighboring `--limit` option's
   existing unbracketed-config-key convention); the regression test was
   strengthened to assert the key text itself, not just the flag name.
2. R1's own requirement text named BOTH `index create --help` (the group) and
   `index create files --help` (the leaf) — only the leaf shipped in the
   original 5-unit plan (that was the CONFIRMed scope; the group surface was
   a gap the final review caught, not a plan violation). Fixed by adding a
   group-level `--engine` callback on `create.app`, mirroring the root app's
   own callback pattern exactly (writes into the same `ctx.obj["engine"]`
   slot via Click's parent→child `obj` inheritance) — verified empirically,
   not just by reasoning about Click internals, and confirmed to leave every
   existing R1 test (leaf position, leaf help, root-only regression,
   existing-collection raw-flag-only replay) untouched. Effective precedence:
   leaf flag > group flag > root flag > env > config > default.
3. R2's "never a silent no-op" requirement was technically violated for
   `--rerank` under `--simple-output` — a prior, independently-verified-correct
   fix had fully suppressed the hint there to protect stdout's JSON purity.
   Resolved by routing the hint to **stderr** under `--simple-output` instead
   of dropping it (`typer.echo(notice, err=True)`) — stdout stays pure,
   parseable JSON; the notice still exists on a channel a human running the
   command would see.
A 4th finding — a 5th surface (`config validate`/`list`/`get`) that still
leaks a raw pydantic dump or shows no warning for a bad `core.engine` value —
was deliberately left unfixed rather than silently expanding scope past the
CONFIRMed 7-requirement plan; recorded in product.md as a known remaining
surface for a future follow-up unit, not fixed ad-hoc mid-review.
**Rationale:** the two-human-gate model (plan→impl, verify→ship) means new
scope discovered during the ship-side review doesn't get silently absorbed
into the CONFIRMed plan's units — genuine requirement gaps the confirmed text
already covered (finding 2) get fixed; genuinely new scope (the 5th surface)
gets documented and deferred instead. Full gate green throughout: ruff/ty/
import-graph clean, full suite 93.30% coverage (>85% required).

### 2026-09-02: Feature 17 (Core v2 Discoverability) shipped; folder wrapped up
**Decision:** Merge PR #191's branch into `main`-tracking state (conflict was
narrow — `.spec/lessons.md` only, both sides had appended new dated entries
at the same spot; every generated/dependency file `main` had moved touched
in the interim — `uv.lock`, workflow YAMLs, `pyproject.toml`, a
`sentence-transformers` rename — merged clean via git's own three-way merge,
verified with `uv lock --check` plus a full re-run of the gate post-merge:
1893 passed, 93.32% coverage). Promoted the durable cross-cutting content and
**deleted** `features/core-v2-discoverability/`: the `--engine`
leaf/group/root precedence pattern (Click hands a child `Context` its
parent's `ctx.obj` by identity — a group/leaf callback writing into it needs
no new resolution tier) and the four-surface engine-error normalizer went to
[tech-app.md](tech-app.md) § Engine Selection; the Rich-swallows-bracketed-
help-text gotcha went to [tech-app.md](tech-app.md) § Markup Safety and
`AGENTS.md` Learnings (broadly reusable — any future `typer.Option(help=...)`
naming a config key is at risk); `--engine`, `index migrate`, and reranking
became shipped rows in [product.md](product.md) § Features, also backfilling
pre-existing drift where Feature 16 (2026-07-19) had shipped without a
features-table update. Two items were deliberately left as **unresolved
follow-up candidates, not spec backlog:** a 5th engine-error surface
(`config validate`/`list`/`get`, found during the feature's final review,
confirmed outside R3/R6's 4-surface scope) and the same `help=`-discards-
docstring pattern already fixed on 5 commands but never audited for full
repo coverage. Neither blocks anything; either is a candidate GitHub issue if
a maintainer wants full closure, not something worth re-opening this spec
for. **Rationale:** a completed feature folder must not linger; durable
cross-cutting content belongs in root specs, resolved fix-by-fix detail
belongs in PR #191 + git history. CODE IS TRUTH — live surface is
`src/indexed/cli/`, `core/engine.py`, `core/v2/`, and `tests/`.

### 2026-08-30: Feature 17 (Core v2 Discoverability, issue #188) opened; scope expanded same day
**Decision:** Capture the five PR #162-review UX findings in
[issue #188](https://github.com/LennardZuendorf/indexed/issues/188) as
Feature 17 rather than fixing ad-hoc: `--engine` invisible on `index create`
subcommands (root-only today, mirrors the existing `--local` pattern for the
fix); reranking has no CLI flag (v2-only, `[core.v2.rerank]` today); `config
set core.engine` prints a raw multi-line pydantic dump instead of the clean
single-line message `--engine`/`INDEXED__CORE__ENGINE` already produce (fix:
reuse `composition.normalize_engine_selector` directly — `config/commands/`
is exempt from the config-package import-purity rule, so no layering
violation); README has zero Core v2 mention; and `index migrate --help`
discards its safety docstring because `knowledge/cli.py` registers it with an
explicit `help=` override. Investigated via 4 parallel research subagents
against `main`, all file:line anchors re-verified by direct reads.
**Same-day follow-up:** on maintainer review, two questions left open by the
initial spec were resolved and two related-but-descoped defects were pulled
into scope rather than left as follow-ups: (1) `--rerank` on a search that
resolves to no v2 collection now must print a one-line hint instead of
silently no-op (`core/versioning.py::detect_engine_version` per searched
collection decides); (2) the config.toml `[core] engine` path gets the same
clean-error fix as `config set` — `resolve_engine_selector`'s config.toml
branch drops `bind()`/pydantic entirely in favor of a raw
`config_service.get("core.engine")` read, closing the last of four surfaces
that can catch a bad engine value; (3) the `help=`-discards-docstring fix
extends from `migrate` to its three siblings (`search`/`inspect`/`update`/
`remove`), same file (`knowledge/cli.py`), same mechanism. The one item that
stays descoped by explicit maintainer choice: a generic Click "did you mean
the top-level flag?" hint for a misplaced `--engine` on the flat commands —
R1's direct fix (surfacing `--engine` on `index create`) already resolves
#188's concrete repro. Now 7 requirements across 5 units (R6 rides with R3's
unit, R7 with R5's). **Rationale:** all seven are discoverability/consistency
gaps on a feature (Core v2) whose safety story already works and is verified
— small, disjoint, no data-loss risk — but worth a spec so each fix carries
its own scenario instead of being patched ad-hoc during a support pass; the
two folded-in defects are the same shape as findings already in the spec, so
fixing them alongside is cheaper than tracking a separate follow-up issue.

### 2026-07-19: Feature 16 (Core v2) shipped; Features 15 + 16 folders wrapped up
**Decision:** Core v2 is implemented (PR #158) and hardened by an end-to-end
testing pass that found two real bugs the unit tests + review missed — v2 was
embedding engine-owned metadata (paths/timestamps/chunk numbers) into every
vector (broke v1 relevance parity R8 and mixed ranking R11; fixed by excluding
metadata from the embed text), and the `v2` engine selector crashed via env/
config (only `--engine` normalized it; fixed in `CoreEngineConfig`'s validator).
Also shipped: distinct reranked `scoreKind`, unified relevance shown in mixed CLI
search, filename-only chunks no longer highlighted as the top result, `--collection`
alias on update/remove/migrate, and quieter missing-collection logs. Marked
Feature 16 DONE. **Wrapped up both owed feature folders:** promoted the core-v2
"Engine routing contract" cross-cutting block into [tech.md](tech.md) § Core
Facade & App Composition Root (correcting the stale "same on-disk format" swap
premise — v2 uses a new version-marked format), compounded the testing lessons
into [lessons.md](lessons.md), then **deleted** `features/core-v2/` and
`features/review-remediation/` (review-remediation had no pending merge blocks;
its content shipped with PR #155). CODE IS TRUTH — live surface is `core/v2/`,
the facade, and `tests/`.
**Rationale:** a completed feature folder must not linger; durable cross-cutting
content lives in root specs, resolved detail in git history. E2E UX testing (not
just green unit tests) is what caught the metadata-in-embedding regression.

### 2026-07-18: Feature 16 (Core v2) opened; Feature 15 closed
**Decision:** Mark Feature 15 DONE (merged to `main` in PR #155; folder
wrap-up owed). Open Feature 16 Core v2: a LlamaIndex-based second engine
coexisting with the frozen v1 engine. Headline decisions (ADRs in the v2
planning doc, since moved to git history / PR #158): v2 uses a **new version-marked on-disk format**
(supersedes the "same on-disk format" swap premise); routing is
**manifest-authoritative** — explicit selectors (`--engine` flag >
`INDEXED__CORE__ENGINE` > `[core] engine` > default v1) apply to *new*
collections only, and a conflicting selector on an existing collection fails
loud; store is SimpleVectorStore with the store identity recorded and
dispatched per collection (FAISS excluded from v2 — LlamaIndex's FAISS
integration lacks delete/filters); embeddings via the native LlamaIndex
HuggingFace integration with v1's exact model — local-only, self-contained,
shared model cache; migration is explicit, offline-by-default, backed up and
reversible; remote providers (Ollama, …), additional stores (Qdrant, …), KG
and hybrid retrieval all deferred to future features behind the shipped
seams.
**Maintainer review 2026-07-18:** `--engine` naming and default-flip criteria
approved; remote providers + Qdrant descoped (units core-v2/5 and core-v2/7
retired); no v1 deprecation planning; PRs #132–#136 closed as superseded and
issues #5/#7 annotated. The prior attempt (PR #86 + splits #132–#136, closed/stale
against the deleted workspace layout) was reviewed: its adapter-at-boundary,
version marker, and mismatch-error patterns are kept; its flag-over-manifest
precedence, delete-before-persist, and hardcoded-FAISS load path are designed
out; recommend closing #132–#136 and annotating issues #5/#7.
**Rationale:** evidence-based reconciliation of the repo's swap-seam design,
the failed first attempt, and verified LlamaIndex capabilities (research in
git history / PR #158; feature folder deleted 2026-07-19).

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
