---
type: feature-tech
feature: simplify
sibling: product.md
parent: ../../tech.md
updated: 2026-07-06
---

# Feature: Simplify — Architecture

How the seven-package workspace collapses into one `indexed` package with four
enforced module edges, how phantom-generality code and mechanism tests are
deleted, how the CLI/config chrome shrinks, and how the process apparatus trims —
all size-only, riding the `foundation` behavior harness so nothing changes for
the user. Size inventory and delete-list evidence: [research.md](research.md).

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

---

## Files (target single-package layout)

```
pyproject.toml                    # the only one; hatchling, no una           ~80
uv.lock                           # regenerated, committed
scripts/check_imports.py          # 4 forbidden edges, AST walk               ~50
src/indexed/
  models.py                       # typed contracts (from foundation)
  protocols.py                    # reader/converter/connector protocols (from foundation)
  utils.py                        # retry + batching (+ slimmed logging)
  config/                         # collapsed from indexed-config             ~450
  core/                           # collapsed from indexed-core (v1 engine); facade in __init__.py
  connectors/                     # collapsed from indexed-connectors
    files/ jira/ confluence/ outline/   # one reader per source
    _url_guard.py change_tracker.py registry.py
  parsing/                        # collapsed from indexed-parsing (content unchanged)
  cli/                            # Typer app; every command file ≤300 lines
  mcp/                            # kept as-is (already right-sized, ~774 LOC)
tests/                            # behavior + system + benchmarks + foundation harness only
AGENTS.md                         # the only one, ≤100 lines
```

Today (verified): 9 `pyproject.toml` (8 project + 1 pandas in `.venv`); 7 real
`AGENTS.md` (root + `apps/indexed` + 5 `packages/*`, 524 lines) each with a
`CLAUDE.md`/`WARP.md` symlink beside it (multi-tool compat, by design — not
duplicated content). Target: one `pyproject.toml`, one root `AGENTS.md` (its
`CLAUDE.md`/`WARP.md` symlinks kept).

## Module edges (replace the workspace + import-graph apparatus)

```
cli, mcp   → core (facade), connectors.registry, config, models, protocols, utils
core       → models, protocols, config, utils           (NEVER connectors / cli / mcp)
connectors → models, protocols, config, parsing, utils  (NEVER core / cli / mcp)
config     → models only
```

Four edges, enforced by `scripts/check_imports.py` (~50 LOC AST walk over one
package's paths), replacing `scripts/check_import_graph.py` (the workspace-wide
checker) in CI. These edges are the core swap seam that `foundation` established;
everything the old workspace used to approximate them — `una`, eight
per-package `pyproject.toml`, protocols-as-a-package, `sync_version.py` — is
deleted here.

## Mechanical collapse procedure (simplify/3, one zero-logic commit)

1. **`git mv` the sources** into `src/indexed/…` (history-preserving):
   `packages/indexed-core/src/core/v1/engine/*` → `src/indexed/core/*`;
   `packages/indexed-connectors/src/connectors/*` → `src/indexed/connectors/*`;
   `packages/indexed-config/src/indexed_config/*` → `src/indexed/config/*`;
   `packages/indexed-parsing/src/*` → `src/indexed/parsing/*`;
   `packages/utils/src/utils/*` → `src/indexed/utils.py` (+ helpers);
   `packages/indexed-protocols/*` → `src/indexed/protocols.py`;
   `apps/indexed/src/indexed/*` → `src/indexed/{cli,mcp}/*`.
2. **Rewrite imports mechanically** — `core.v1.engine.*` → `indexed.core.*`,
   `connectors.*` → `indexed.connectors.*`, `indexed_config.*` →
   `indexed.config.*`, etc. Pure text rewrite; no logic edit rides along.
3. **Remove the workspace apparatus** — delete `[tool.una]` and the
   `una>=0.7.0` dependency from root `pyproject.toml` (lines 108, 123);
   delete the 8 per-package `pyproject.toml`; delete `scripts/sync_version.py`;
   fold all deps into the one `pyproject.toml` with a single hatchling build and
   two console scripts (`indexed`, MCP server). Regenerate + commit `uv.lock`.
4. **Add `scripts/check_imports.py`**; wire it into CI in place of the old
   graph checker.
5. **Wheel smoke** — build in a clean venv, install, run `indexed --help` and
   the MCP `--help`; run the full suite + a real create/search/update on both
   sides of the commit. No behavior diff permitted.

## DELETE-LIST (dead code — simplify/2)

| Symbol / file | Location (current tree) | LOC | Why |
|---|---|---|---|
| `SearchArgs` DTO | `core/v1/engine/services/search_service.py:369` | — | zero usages |
| `CONFIG_REGISTRY`, `get_config_class`, `list_connector_types` | `connectors/registry.py` | — | zero production consumers; tests only |
| Indexer registry | `core/v1/engine/indexes/indexer_registry.py` | 163 | one indexer exists (`faiss_indexer.py`) |
| Indexer factory | `core/v1/engine/indexes/indexer_factory.py` | 97 | naming scheme for a single impl |
| Multi-indexer loops + `manifest["indexers"][0]` asymmetry | `documents_collection_creator.py` | — | lists/loops over one indexer |
| `indexing_batch_size=500_000` batching | `documents_collection_creator.py` | — | batch that never batches |
| `_UpdatingCollectionCreator` wrapper + `get_raw()` alias | core creator/service | — | wrapper with no second behavior |
| Sync confluence-cloud reader | `connectors/confluence/confluence_cloud_document_reader.py` | 293 | never instantiated; async reader borrows only its static helpers |
| Two-progress-callback system | core/CLI progress (`ProgressCallback` + `PhasedProgressCallback`) | — | collapse to the one `foundation` progress protocol; drop magic phase-string coupling |

## DELETE-LIST (tests — split across foundation/1, simplify/2, simplify/5)

The brittle *mechanism* tests are pruned earlier, in **foundation/1**'s altitude
pass, so they don't fight the collapse/contract work — this feature does not
re-hunt them. Listed here for provenance:

- `tests/**/test_core_shims.py` — tautological re-export shim test. → **foundation/1**
- 4× registry-membership `test_init.py` clones — assert registry contents. → **foundation/1**
- Protocol-conformance stub tests — assert a stub implements a protocol. → **foundation/1**
- Tests paired with code deleted in simplify/2 (SearchArgs, indexer-registry/
  factory, dead confluence sync reader, `CONFIG_REGISTRY`/`get_config_class`). → **simplify/2** (die with the code)
- 632 LOC testing `migration.py` — one-time legacy code, dies with `migration.py`. → **simplify/4**
- ~3,770 LOC of Rich-component markup tests — assert rendered chrome markup. → **simplify/5** (residual size cleanup)

Deletion is category-at-a-time with `uv run pytest -q` green between categories;
any test that reddens the suite pinned behavior and stays. Keep: behavior,
`tests/system/`, `tests/benchmarks/`, and the `foundation` `tests/characterization/`
harness.

## Generic schema-driven `create` (simplify/4)

`create.py` is 992 LOC — four near-identical ~230-line command clones (files,
jira, confluence, outline). Collapse to ~250 LOC: one command parameterized by a
per-source spec (source name → its `SourceConfig` schema fields, prompts,
Cloud/Server detection, credential routing). Field iteration is schema-driven,
so a new source is a spec entry, not a cloned command. Behavior is identical per
source (per-source create parity, product R3). This deletes the four-way
divergence in empty-input handling and Cloud/Server routing — but those are
*behavior* fixes owned by `foundation`; this unit only removes the duplication
after they land, keeping the merged command byte-behavior-equal to the fixed
clones.

## Config CLI shrink (simplify/4)

`config/cli.py` is 1,959 LOC (larger than the whole 1,584-LOC config package it
fronts). Reduce to ~300 LOC over four subcommands — `get`, `set`, `list`,
`validate` — backed by the read-mostly `config` service `foundation` builds
(`get_config()`/`set_value()`). Delete `apps/indexed/src/indexed/utils/migration.py`
(259 LOC, one-time legacy still shipping) and its `config update`/`--file`
surface. No command file exceeds 300 lines after the shrink.

## Rich-component pruning (simplify/4)

Prune the bespoke Rich component library (cards, panels, themed renderers) to
the components actually rendered by surviving commands. The ~3,770 LOC of
Rich-markup *tests* go with them (simplify/5). Rendering/escaping correctness is
`foundation`'s; this only deletes unrendered components and their tests.

## Process-apparatus removal (simplify/1)

- **Unvendor `.agents/skills/`** — the checked-in skill tree is ~12,592 LOC
  (`.agents/` measures 10,885 LOC of `.md`/`.py`/`.sh` in the current tree),
  larger than core+config+connectors combined. Delete it; install via
  `skills-lock.json`.
- **One `AGENTS.md`** — absorb the 6 per-package real `AGENTS.md` (`apps/indexed`
  + 5 `packages/*`) into the root `AGENTS.md` ≤100 lines, and delete their
  dangling `CLAUDE.md` symlinks. **Keep** the root `CLAUDE.md`/`WARP.md`
  symlinks → `AGENTS.md`: that multi-tool-compat pattern is deliberate, it just
  applies to one file now instead of seven.
- **CI trim** — reduce to lint (ruff) + type-check (mypy) + test (pytest) +
  import-check (`check_imports.py`) + wheel-smoke (clean-venv `--help`); move
  benchmarks to an on-demand workflow.

## Link

Evidence — LOC-per-package table, file/pyproject counts, dead-weight delete-list,
process-apparatus numbers, good-bones keep-list, target metric:
[research.md](research.md).

<!-- merge -->
## Architectural rules (post-simplify)

- **One package, four module edges** (`cli`/`mcp` → `core`|`connectors`|`config`;
  `core ↛ connectors`; `connectors ↛ core`; `config` leaf), enforced by
  `scripts/check_imports.py`. One `pyproject.toml`, one wheel (`indexed-sh`), no
  `una`, no per-package builds, no `sync_version.py`.
- **No phantom generality.** No abstraction (registry/factory/multi-impl loop)
  over a single implementation. One indexer, one progress protocol, no dead DTOs
  or re-export shims.
- **Behavior-only tests.** Keep behavior/system/benchmark + the characterization
  harness; no mechanism tests (registry membership, shims, protocol stubs, Rich
  markup, migration). **Coverage gate is scoped to `core`/`connectors`/`config`;
  UI chrome (`cli`/`mcp`) is exempt.**
- **One root `AGENTS.md`** (≤100 lines); agent skills install from
  `skills-lock.json`, never vendored.
<!-- /merge -->

## Risks

1. **Big-bang rename (simplify/3).** Mitigation: one zero-logic commit, `git mv`
   to preserve history, mechanical import rewrite only; full suite + a real
   `create/search/update` on both sides of the commit; `foundation` harness must
   stay green.
2. **Wheel regression on `una` removal.** Mitigation: clean-venv wheel smoke in
   CI — build, install, run `indexed --help` and MCP `--help`; keep a trimmed
   wheel-validation step.
3. **Deleting a test that secretly caught behavior.** Mitigation: delete
   mechanism tests by category with the suite green between categories; any
   deletion that reddens the suite is reverted (it pinned behavior).
4. **Coverage floor after UI exemption** applies to a smaller base. Mitigation:
   confirm ≥85% on `core`/`connectors`/`config` alone before rescoping.
