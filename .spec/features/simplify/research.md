---
type: feature-research
feature: simplify
sibling: product.md
parent: ../../tech.md
updated: 2026-07-06
---

# Feature: Simplify — Research (size inventory)

The evidence base for Codebase Reduction: how big each area is, what is dead
weight, what is worth keeping, and the target metric. Numbers verified against
the tree at branch `claude/architecture-audit-review-kkeihg` (2026-07-06 audit)
and re-confirmed with `wc -l` / `find` on 2026-07-06.

## Size inventory (verified)

| Area | LOC | Note |
|---|---|---|
| apps/indexed src | 9,764 | 45% of all source is the "thin UI layer" |
| indexed-connectors src | 5,548 | 4 sources |
| indexed-core src | 3,020 | the actual engine |
| indexed-config src | 1,584 | reads/writes TOML + .env |
| parsing / utils / protocols | 828 / 588 / 269 | |
| tests | 25,244 | 1.17× source; 1,410 test functions |
| `.agents/` vendored skills | 12,592 | larger than core+config+connectors combined |
| `config/cli.py` alone | 1,959 | larger than the whole config package it fronts |
| `create.py` | 992 | 4 near-identical ~230-line command clones |

Proportion: a ~3k engine under ~18k of chrome (apps 9.8k + connectors 5.5k +
config 1.6k) + ~25k tests + ~15k process apparatus.

## File / build counts (verified 2026-07-06)

- **9 `pyproject.toml`** total — 8 project files (root + `apps/indexed` + 6
  `packages/*`) + 1 vendored `pandas` under `.venv`. Target: **1**.
- **14 contract docs** — `AGENTS.md` + `CLAUDE.md` twins under root,
  `apps/indexed`, and 5 `packages/*`. Target: **1 `AGENTS.md` ≤100 lines**.
- `una` wired in root `pyproject.toml` at `[tool.una]` (line 108) and
  `una>=0.7.0` dependency (line 123). Target: **removed**.
- `scripts/sync_version.py` and `scripts/check_import_graph.py` present. Target:
  delete `sync_version.py`; replace the graph checker with
  `scripts/check_imports.py` (~50 LOC).
- `.agents/` measures **10,885 LOC** of `.md`/`.py`/`.sh` in the current tree
  (audit cited 12,592 for the vendored skills subtree). Target: **unvendored**.

## Dead weight (delete-list)

- `SearchArgs` DTO (`search_service.py:369`) — zero usages.
- `CONFIG_REGISTRY`, `get_config_class`, `list_connector_types`
  (`connectors/registry.py`) — zero production consumers; tests only.
- Indexer registry/factory naming scheme (`indexer_registry.py` 163 +
  `indexer_factory.py` 97) — exactly one indexer exists (`faiss_indexer.py`).
- Multi-indexer lists/loops + `manifest["indexers"][0]` asymmetry;
  `indexing_batch_size=500_000` batching that never batches.
- Sync `confluence_cloud_document_reader.py` (293 LOC) — never instantiated;
  async reader borrows its static helpers only.
- `_UpdatingCollectionCreator` wrapper class; `get_raw()` alias; tautological
  `test_core_shims.py`; 4× registry-membership `test_init.py` clones;
  protocol-conformance stub tests; ~3,770 LOC of Rich component markup tests;
  632 LOC testing `migration.py` (itself one-time legacy code — 259 LOC at
  `apps/indexed/src/indexed/utils/migration.py` — still shipping).
- Two parallel progress systems (`ProgressCallback` + `PhasedProgressCallback`)
  coupled by magic phase-name strings across the core/CLI boundary.

## Process apparatus (delete / trim)

- `.agents/skills/` vendored tree — ~12,592 LOC; unvendor, install via
  `skills-lock.json`.
- 14 `AGENTS.md`/`CLAUDE.md` → one root `AGENTS.md` ≤100 lines.
- 8 project `pyproject.toml` + `una` + `sync_version.py` → one build.
- CI → lint + mypy + test + import-check + wheel-smoke; benchmarks on-demand.

## Worth keeping (the good bones)

- Atomic disk persistence (`disk_persister.py`: tmp → fsync → `os.replace`).
- Lazy ML imports (<1s startup discipline) and searcher caching
  (`SearchService._searcher_cache`).
- `_url_guard.py` off-origin credential guard; `change_tracker.py`
  (git/hash/mtime incremental indexing — a differentiating feature).
- The reader/converter split + `BaseConnector` idea (4 sources onboarded) —
  keep the protocol, drop the package around it.
- `retry.py` + `batch.py`; the MCP layer's proportions (~774 LOC total);
  system/e2e/benchmark tests; static `CONNECTOR_REGISTRY` (post-audit form).
- The `foundation` characterization harness — the net that gates deletion.

## Target metric

Repo **~66k → ~15k** total lines. **One package**; **≤~6k src**; **≤~8k tests**;
**one `AGENTS.md`** — without losing the good bones above (atomic persistence,
lazy imports, searcher caching, `_url_guard`, `change_tracker`, connector
protocol, MCP layer, the foundation harness).
