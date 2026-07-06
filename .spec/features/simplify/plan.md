---
type: feature-plan
feature: simplify
sibling: tech.md
parent: ../../plan.md
updated: 2026-07-06
---

# Feature: Simplify — Implementation Plan

Six units that reduce the repository from ~66k lines to ~15k without changing
behavior: peel the process apparatus, delete phantom generality and its
mechanism tests, collapse the seven-package workspace into one, shrink the
CLI/config chrome, right-size the test corpus, then lock size gates and compound
the new rules. Each deletion rides on the `foundation` characterization harness,
so the suite proves behavior is preserved between every step.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Starts when Feature `foundation` is `DONE` (root
[plan.md](../../plan.md) Feature Sequence). `foundation` leaves behind the
behavior harness, typed contracts (`models.py`/`protocols.py`), and the core
facade — the net that makes big-bang deletion and collapse safe. This feature
depends on the whole upstream feature, not on any of its individual units.

---

## Problem Frame

The engine is ~3,020 LOC. Everything around it is disproportionate: apps/CLI is
9,764 LOC (45% of all source, "the thin UI layer"), connectors 5,548, config
1,584 — call it ~18k of chrome over a 3k engine. Tests are 25,244 LOC (1.17×
source, 1,410 test functions), a large fraction asserting mechanism (registry
membership, shims, protocol stubs, ~3,770 LOC of Rich-markup tests, 632 LOC on
one-time `migration.py`). The process apparatus is another ~15k: `.agents/`
vendored skills alone are 12,592 LOC — larger than core+config+connectors
combined — plus fourteen `AGENTS.md`/`CLAUDE.md` files and eight per-package
`pyproject.toml`s under a `una` bundler. `config/cli.py` is 1,959 LOC (bigger
than the whole config package it fronts); `create.py` is 992 LOC of four
~230-line clones. None of this is behavior — it is generality with no second
implementation, tests of internal shape, and vendored tooling. The order below
peels from the outside in (lowest runtime risk first) so the risky move — the
workspace collapse — happens on an already-thinned tree with the harness green.

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Single package](product.md#requirement-single-package) | simplify/3 |
| R2 | [No phantom generality](product.md#requirement-no-phantom-generality) | simplify/2 |
| R3 | [Right-sized CLI](product.md#requirement-right-sized-cli) | simplify/4 |
| R4 | [Behavior-only tests](product.md#requirement-behavior-only-tests) | simplify/2, simplify/5 |
| R5 | [Right-sized process apparatus](product.md#requirement-right-sized-process-apparatus) | simplify/1, simplify/6 |

Every unit below cites the R-IDs it satisfies. Do not renumber R-IDs.

---

## Key Technical Decisions

1. **Peel outside-in: process → dead-code → collapse → chrome → tests.** Order
   by runtime risk. Unvendoring skills and merging docs (simplify/1) touches no
   runtime code. Deleting zero-consumer symbols (simplify/2) is gated on the
   harness covering the surviving behavior. Only then the big mechanical
   collapse (simplify/3), then semantic shrinks (simplify/4–5) on the final
   coordinates so every reviewed diff is in its permanent location.
2. **The `foundation` harness is the net that makes deletion safe.** Every
   symbol deleted in simplify/2 and every test deleted in simplify/5 is gated on
   a behavior/system/characterization test still covering that behavior. The
   suite stays green *between* deletion categories, not just at the end — a
   deletion that reddens the suite has removed behavior, not dead weight.
3. **Architecture-first, then collapse (user decision, 2026-07-06).** The
   `foundation` architecture (facade, typed contracts, corrected wiring) lands
   in the *current* seven-package coordinates; the workspace collapse
   (simplify/3) happens afterward here. This accepts churn — architecture is
   written in old paths, then `git mv`'d — in exchange for shipping correctness
   without waiting on a repo-wide rename. The churn is mitigated by making the
   collapse a single zero-logic commit (`git mv` + mechanical import rewrite)
   verified by the harness on both sides. Collapse-first was considered and
   declined (see Open Questions).
4. **Collapse is one zero-logic commit.** `git mv` preserves history; the import
   rewrite is purely mechanical (`core.v1.engine.*` → `indexed.core.*`, etc.).
   No behavior edit rides along; the semantic shrinks (simplify/4) are separate
   commits on the collapsed tree so they review cleanly.
5. **Delete tests by category with the suite green between categories.** Removing
   mechanism tests risks removing a test that secretly pinned behavior;
   category-at-a-time deletion with a green gate between each isolates any such
   loss to one category.

---

## Unit IDs

Units are `simplify/n` — assigned once, never renumbered on reorder. Cite IDs in
commits and tests during impl (`refactor(simplify): simplify/3 ...`).

---

### simplify/1 — Process apparatus reduction

**Goal:** Shrink the engineering apparatus with zero runtime-code change:
unvendor the checked-in agent skills, collapse fourteen contract docs to one
root `AGENTS.md`, trim CI.

**Requirements:** R5

**Dependencies:** —

**Files:**

```
.agents/skills/**                          # DELETE vendored tree (~12.6k LOC), install via skills-lock.json
skills-lock.json                           # ensure it pins the unvendored skills
AGENTS.md                                   # rewrite as the ONE contract, ≤100 lines
packages/*/AGENTS.md packages/*/CLAUDE.md   # DELETE (absorb into root)
apps/indexed/AGENTS.md apps/indexed/CLAUDE.md  # DELETE (absorb into root)
.github/workflows/*.yml                     # trim to lint+mypy+test+import-check+wheel-smoke; benchmarks on-demand
```

**Test scenarios:**

- Exactly one `AGENTS.md` remains, at the root, ≤100 lines.
- No `.agents/skills/` tree is checked in; skills resolve from the lockfile.
- CI runs only the trimmed gate set; benchmark workflow is on-demand.

**Verification:** `find . -name AGENTS.md -not -path './.venv/*'` → one path;
`wc -l AGENTS.md` ≤100; skills list resolves from lock; CI config diff shows the
trimmed jobs. Full suite unchanged (no runtime code touched).

---

### simplify/2 — Dead code + mechanism-test deletion

**Goal:** Delete every zero-second-implementation symbol and its mechanism
tests, in the current seven-package tree, suite green between categories.

**Requirements:** R2, R4

**Dependencies:** — (requires the `foundation` harness to cover surviving
behavior — a cross-feature gate satisfied by the feature gate above)

**Files:** (see the DELETE-LIST in [tech.md](tech.md))

```
packages/indexed-core/src/core/v1/engine/services/search_service.py   # SearchArgs DTO
packages/indexed-connectors/src/connectors/registry.py                # CONFIG_REGISTRY/get_config_class/list_connector_types
packages/indexed-core/src/core/v1/engine/indexes/indexer_registry.py  # DELETE (163)
packages/indexed-core/src/core/v1/engine/indexes/indexer_factory.py   # DELETE (97)
packages/indexed-core/.../documents_collection_creator.py             # multi-indexer loops, indexers[0] asymmetry, 500k batching
packages/indexed-core/.../ (updating-creator wrapper)                 # _UpdatingCollectionCreator, get_raw() alias
packages/indexed-connectors/src/connectors/confluence/confluence_cloud_document_reader.py  # DELETE (293), sync, never instantiated
packages/indexed-core/.../progress (PhasedProgressCallback path)      # collapse two progress systems to one
tests/**                                                              # test_core_shims.py, 4× registry test_init clones, protocol-stub tests
```

**Test scenarios:**

- Grep for each deleted symbol name returns no production or test reference.
- The full suite passes after each deletion category, not just at the end.
- Create→search→update→remove per source still returns known hits (harness).

**Verification:** `uv run pytest -q` green after each category; grep for every
deleted symbol is empty; `uv run mypy` adds no new errors on touched files.

---

### simplify/3 — Workspace collapse to single package

**Goal:** One zero-logic commit collapsing seven packages into `src/indexed/…`,
rewriting imports, dropping `una`/eight pyprojects/`sync_version.py`, adding the
slim import check.

**Requirements:** R1

**Dependencies:** simplify/2

**Files:**

```
packages/*/src/* apps/indexed/src/indexed   # git mv → src/indexed/{core,connectors,config,parsing,cli,mcp,...}
pyproject.toml                              # single hatchling build; remove [tool.una] and una>=0.7.0 dep
packages/*/pyproject.toml apps/indexed/pyproject.toml  # DELETE (8 files)
scripts/sync_version.py                     # DELETE
scripts/check_import_graph.py               # REPLACE with scripts/check_imports.py (~50 LOC, 4 edges)
uv.lock                                     # regenerate + commit
```

**Test scenarios:**

- Wheel builds in a clean venv; `indexed --help` and MCP `--help` succeed.
- Create/search/update on a real collection behaves identically pre/post move.
- `scripts/check_imports.py` passes and rejects the four forbidden edges.

**Verification:** clean-venv wheel smoke (`indexed --help`, MCP `--help`);
`uv run pytest -q` green; `git log --follow` shows preserved history on moved
files; `python scripts/check_imports.py` exits 0.

---

### simplify/4 — CLI/config chrome shrink

**Goal:** Replace the four `create` clones with one schema-driven command,
reduce the config CLI to four subcommands, delete `migration.py`, prune Rich
components, keep every command file under 300 lines.

**Requirements:** R3

**Dependencies:** simplify/3

**Files:**

```
src/indexed/cli/.../create.py               # 992 → ~250, one schema-driven command over source specs
src/indexed/config/cli.py                   # 1,959 → ~300, get/set/list/validate only
src/indexed/.../utils/migration.py          # DELETE (259) + its tests (632)
src/indexed/cli/.../cards.py + Rich components  # prune to rendered components
src/indexed/cli/composition.py              # lazy connector-registry build for <1s startup
```

**Test scenarios:**

- Per-source create parity: each source yields a searchable collection.
- `config get/set/list/validate` round-trip; removed subcommands are gone.
- No command file exceeds 300 lines; startup stays <1s.

**Verification:** `uv run pytest -q -k "create or config"` green; per-file
`wc -l` on `cli/**` all ≤300; startup timing check <1s; grep for `migration`
empty.

---

### simplify/5 — Test right-sizing + coverage rescope

**Goal:** Delete the remaining mechanism tests (Rich-markup rendering, migration,
protocol stubs), rescope coverage to core/connectors/config with UI exempt, hit
the ≤~8k test-LOC target.

**Requirements:** R4

**Dependencies:** simplify/3

**Files:**

```
tests/**                                    # DELETE Rich-markup tests (~3.8k), migration tests, stub tests
pyproject.toml / .coveragerc                # scope coverage to core/connectors/config; exempt cli/mcp UI
```

**Test scenarios:**

- A no-op internal rename leaves the suite green (no structural assertions left).
- Coverage gate on core/connectors/config stays ≥85%.
- Test corpus reduced toward ≤~8k LOC.

**Verification:** `uv run pytest -q --cov` green ≥85% on scoped packages;
`find tests -name '*.py' | xargs wc -l` total trends to target; rename-smoke
passes.

---

### simplify/6 — Final size gates + COMPOUND docs

**Goal:** Assert the whole-repo size gates, promote the merge-marked
architectural rules to root specs, update the root plan.

**Requirements:** R5

**Dependencies:** simplify/4, simplify/5

**Files:**

```
scripts/check_imports.py + a size-gate check   # one package; ≤~6k src; ≤~8k tests; one AGENTS.md
.spec/tech.md .spec/tech-*.md                   # promote the <!-- merge --> block from tech.md
.spec/plan.md                                   # update root plan (orchestrator-owned; note completion)
AGENTS.md                                       # final ≤100-line contract reflects one-package reality
```

**Test scenarios:**

- Size gates pass: one package, ≤~6k src LOC, ≤~8k test LOC, one `AGENTS.md`.
- Root `.spec/tech.md` carries the post-simplify architectural rules.

**Verification:** size-gate script exits 0; `bash
.agents/skills/spec/scripts/validate.sh` → 0 errors after promotion; full gate
(ruff/mypy/pytest) green.

---

## Dependencies

| Unit | Blocks | Blocked by |
|---|---|---|
| simplify/1 | — | — |
| simplify/2 | simplify/3 | — (foundation harness, via feature gate) |
| simplify/3 | simplify/4, simplify/5 | simplify/2 |
| simplify/4 | simplify/6 | simplify/3 |
| simplify/5 | simplify/6 | simplify/3 |
| simplify/6 | — | simplify/4, simplify/5 |

Same-feature dependencies only. The cross-feature gate (`foundation` DONE) is a
whole-feature edge in the root Feature Sequence, not a unit edge here.

---

## Progress

| Unit | Status |
|---|---|
| simplify/1 | NOT STARTED |
| simplify/2 | NOT STARTED |
| simplify/3 | NOT STARTED |
| simplify/4 | NOT STARTED |
| simplify/5 | NOT STARTED |
| simplify/6 | NOT STARTED |

---

## Open Questions

1. **Collapse-first was considered and declined.** The alternative was to
   collapse the workspace to one package *before* `foundation`'s architecture
   work, so correctness lands in final coordinates. Declined (user decision,
   2026-07-06): it would block every bug fix behind a repo-wide rename and force
   the harness to be written twice. Chosen: architecture-first in old
   coordinates, then a single zero-logic `git mv` collapse here, accepting the
   churn because `git mv` + the harness make the move mechanically safe.
