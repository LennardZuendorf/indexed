---
type: feature-research
feature: architecture-audit
cluster: systemic
parent: ../product.md
updated: 2026-06-29
---

# Research: Cross-Cutting Monorepo Findings

Discovery artifact from the 2026-06-29 deep architecture audit. Synthesizes
14 parallel package/app audits into systemic issues, dependency violations, v2
readiness, test layout, refactor sequence, and disposition matrix.

**Related:** [product.md](../product.md) R1–R11. [plan.md](../plan.md).
Cluster docs: [core.md](core.md), [connectors.md](connectors.md),
[config.md](config.md), [parsing-utils.md](parsing-utils.md), [app.md](app.md).

---

## Summary

The monorepo is **architecturally bisected**: foundation (`indexed-config`,
`indexed-parsing`, `utils`) and app shell (CLI/MCP decomposition) follow
`.spec/tech.md` § Architectural Rules. **Critical debt** sits at the v1
engine ↔ connectors boundary — a declared and runtime circular dependency blocks
v2. Infrastructure is ~**75%** v2-ready; core/connectors are ~**15%** ready (no
`core/v2/`, entangled services, cycle in `pyproject.toml`). Fix the dependency
graph first (Phase 0), delete speculative v1 code, then scaffold v2 — do not
keep polishing v1 orchestration.

---

## Top 10 Systemic Issues

| # | Severity | Issue | Packages affected | Spec rule violated |
|---|----------|-------|-------------------|-------------------|
| **1** | **P0** | Core ↔ connectors circular dependency (declared in `indexed-core/pyproject.toml` + runtime imports) | core, connectors | Dependency Direction |
| **2** | **P0** | Protocols in wrong layer — connectors import `core.v1.connectors.*`; core imports connectors back | core, connectors | "Core MUST NOT import concrete connectors" |
| **3** | **P0** | Three connector instantiation paths (`collection_service` switch, `connectors/registry.py`, `create.py` hardcoded commands) | core, connectors, app | DI / no dual code paths |
| **4** | **P0** | CLI/MCP storage path divergence — MCP never passes `collections_path`; global `--local` broken | app, core, config | MCP parity / single-source |
| **5** | **P1** | Import-time config registration in `core/v1/__init__.py`, connector `__init__.py` files | core, connectors | No Import-Time Side Effects |
| **6** | **P1** | Undeclared pyproject deps — core uses `indexed_config`; connectors use `indexed_config` + core protocols | all | Monorepo integrity |
| **7** | **P1** | Dual config read models — `read_for_mode()` spec-correct; `TomlStore.read()` still merges | config, app | Single-source config |
| **8** | **P1** | File size limits systematically exceeded (`config/cli.py` 1959L, `create.py` 967L, god services 400L+) | app, core | File Size Limits |
| **9** | **P2** | Services misplaced in core with connector wiring; "app services" live in `core/v1/engine/services/` | core, app | Thin Commands, Fat Services |
| **10** | **P2** | Core undertested (5 unit files vs 31 source modules); test mirror drift | tests, core | Testing Strategy |

---

## Dependency Violation Matrix

**Declared edges (pyproject.toml):**

```text
indexed (app) → core, connectors, parsing, config, utils
core          → utils, connectors          ← SPEC VIOLATION
connectors    → utils, parsing             ← missing: core, config (runtime)
config, parsing, utils → standalone ✓
```

| From ↓ / To → | **indexed** | **core** | **connectors** | **config** | **parsing** | **utils** |
|---------------|:-----------:|:--------:|:--------------:|:----------:|:-----------:|:---------:|
| **indexed** | — | ✓ spec | ✓ spec | ✓ spec | ✓ declared | ✓ spec |
| **core** | ✗ | — | **✗ 4 files** | ✓ (undeclared) | ✗ | ✓ spec |
| **connectors** | ✗ | ✓ protocols | — | ✓ (undeclared) | ✓ spec | ✓ spec |
| **config** | ✗ | ✗ | ✗ | — | ✗ | ✗ |
| **parsing** | ✗ | ✗ | ✗ | ✗ | — | ✗ |
| **utils** | ✗ | ✗ | ✗ | ✗ | ✗ | — |

**Core → connectors violations (concrete):**

| File | Violation |
|------|-----------|
| `create_collection_factory.py:3` | Top-level `from connectors.document_cache_reader_decorator` |
| `collection_service.py:38–94` | Hardcoded connector imports in `_build_connector_from_config` |
| `update_collection_factory.py:155,375–376` | Registry + concrete `FileSystemConnector` / reader |
| `index.py:79` | Docstring reference (not runtime import) |

**Connectors → core:** `core.v1.connectors.metadata.ConnectorMetadata` in 4 connector
modules — acceptable only after protocols move to a lower package.

---

## v2 Readiness

| Area | v1 state | v2 readiness | Blocker |
|------|----------|--------------|---------|
| Config + schema versioning | Shipped (`core.v1.*`) | **Ready (~75%)** — add `core.v2.*` registration | None |
| Exception hierarchy | `IndexedError` in config; app extensions unused | **Ready** | Wire at boundaries (R6) |
| Utils / parsing | Clean layers, lazy imports | **Ready (~75%)** | Minor relocations |
| CLI / MCP shell | MCP decomposed; fat commands remain | **Partial (~60%)** | #119 thin commands; storage parity |
| Core engine | All in `v1/`, coupled to connectors | **Not ready (~15%)** | Cycle + misplaced orchestration |
| Connectors | Import core protocols; import-time config | **Not ready (~15%)** | Depends on protocols extraction |
| Public API | `core.v1.Index` facade bypassed by CLI/MCP | **Needs v2 facade** | No scaffold |
| Feature spec | None under `.spec/features/` for v2 | **Not started** | Plan requires spec before impl |

**Overall:** Infrastructure **~75%**. Core/connectors **~15%**.

---

## Test Layout Drift

| Package | Source `.py` | Unit test files | Ratio | Mirror quality |
|---------|-------------|-----------------|-------|----------------|
| `indexed` (app) | 47 | 32 | 0.68 | Good breadth |
| `indexed-core` | 31 | **5** | **0.16** | **Poor — undertested** |
| `indexed-connectors` | 34 | 25 | 0.74 | Good |
| `indexed-config` | 10 | 10 | 1.0 | Excellent |
| `indexed-parsing` | 6 | 5 | 0.83 | Good |
| `utils` | 6 | 5 | 0.83 | Good |

**Structural drift:**

| Path | Actually tests | Issue |
|------|----------------|-------|
| `tests/unit/indexed/services/` | `core.v1.engine.services.*` | **Misplaced** — should be `tests/unit/indexed_core/services/` |
| `tests/unit/indexed/connectors/` | App-level dynamic registry | OK (app-specific) but overlaps connectors package tests |
| `tests/unit/tools/` | Version sync utility | Orphan — not package-aligned |

**Integration balance:** ~90% unit, ~6.5% system (`tests/system/`), ~2% benchmarks.
Unit-heavy is appropriate; **core engine lacks proportional coverage**. Expand
characterization tests before v2 refactor.

---

## Recommended Refactor Sequence

### Phase 0 — Unblock the graph (P0, ~1 sprint)

Maps to architecture-audit/1–4.

- [ ] Create `packages/indexed-protocols/` — `BaseConnector`, metadata, `SourceConfig`, progress types
- [ ] Remove `indexed-connectors` from `indexed-core/pyproject.toml`
- [ ] Move connector resolution to app composition root (`bootstrap.py` + registry)
- [ ] Move `CacheReaderDecorator` to core or protocols (currently pulled from connectors)
- [ ] Add missing declared deps; import-graph CI check
- [ ] Introduce `resolve_collections_context()` shared by CLI + MCP

### Phase 1 — Hygiene (P1, ~1 week, parallel-friendly)

Maps to architecture-audit/5–8.

- [ ] Remove import-time config registration; single `register_app_config()` in bootstrap
- [ ] Unify config read on `read_for_mode()` only; delete merge path
- [ ] Consolidate HTTP retry in `connectors/http.py` or extended `utils/retry.py`
- [ ] Delete speculative code: `FaissAutoIndexer`, deprecated wrappers, dead DTOs
- [ ] Remove core import-time logging setup
- [ ] Relocate utils helpers (batch/retry → connectors; performance → core)

### Phase 2 — v2 engine scaffold (P0 for rewrite, ~2 sprints)

- [ ] Create `.spec/features/core-v2/` per plan routing
- [ ] Add `core/v2/` parallel to `v1/` — protocol-only inputs, no connector imports
- [ ] Port engine primitives: creator, searcher, FAISS, embedder, persister
- [ ] Register `CoreV2*` config namespaces
- [ ] Characterization tests: adapt existing core tests → `tests/unit/indexed_core/v2/`

### Phase 3 — v2 connectors (~2 sprints)

- [ ] Rewrite connectors against `indexed-protocols` only (not core engine)
- [ ] Single registry consumed by app composition root
- [ ] Keep v1 path for backward compat during alpha

### Phase 4 — App layer cleanup (P1, #119)

Maps to architecture-audit/11 + issue #119.

- [ ] Extract `knowledge/services/` from fat command files
- [ ] Split `config/cli.py`, `create.py` (<150L per command file)
- [ ] `search_facade.py` for CLI/MCP parity
- [ ] Wire `IndexedError` handlers CLI/MCP
- [ ] Move `tests/unit/indexed/services/` → `tests/unit/indexed_core/services/`

### Phase 5 — Cutover & retire v1 (P2)

- [ ] MCP/CLI default to v2 services with v1 migration path
- [ ] Deprecate `core.v1.Index` facade
- [ ] Delete `v1_adapter` when core accepts typed documents
- [ ] Remove v1 code after alpha users migrated

---

## Delete / Merge / Keep / Defer Matrix

| Component | Path(s) | Action | Why | When |
|-----------|---------|--------|-----|------|
| **FaissAutoIndexer + auto registry** | `faiss_auto_indexer.py`, `indexer_registry.py`, `indexer_factory.py` | **DELETE** | Spec: FlatL2 only; untested; incremental-update risk | Quick win |
| **Deprecated Jira/Confluence converter wrappers** | `jira/jira_*_document_converter.py`, `confluence/confluence_*_document_converter.py` | **DELETE** | ~600 LOC; unified classes exist | Quick win |
| **`PathsConfig` DTO** | `core/v1/config_models.py` | **DELETE** | Zero runtime consumers | Quick win |
| **`utils.safe_getattr`** | `utils/safe_getattr.py` | **DELETE** | Test-only usage | Quick win |
| **Unimplemented embedding providers** | `CoreV1EmbeddingConfig.provider` / `api_key_env` | **DELETE fields** | openai/voyage documented but not implemented | Quick win |
| **`TomlStore.read()` merge path** | `indexed_config/store.py` | **DELETE** | Contradicts single-source spec | Phase 1 |
| **`DOCLING_FALLBACK` strategy** | `parsing/router.py` | **DELETE** | YAGNI | Quick win |
| **`ConfigRegistry` dict wrapper** | `indexed_config/registry.py` | **MERGE → service.py** | YAGNI | Phase 1 |
| **`Index` façade** | `core/v1/index.py` | **MERGE → services** | CLI/MCP bypass it; only `remove.py` uses it | Quick win |
| **Triple connector builders** | `collection_service`, `registry.py`, `create.py` | **MERGE → registry** | Single seam for v2 | Phase 0–1 |
| **Dual config registries** | `connectors/registry.py` vs `apps/indexed/connectors/` | **MERGE** | No dual code paths | Phase 1 |
| **Deprecated Jira reader wrappers** | `jira/jira_document_reader.py`, `jira_cloud_document_reader.py` | **MERGE → UnifiedJiraDocumentReader** | Wrappers on hot path | Pre-v2 |
| **orjson/json shims (×3)** | core engine modules | **MERGE → utils/json_io.py** | DRY | Phase 1 |
| **`tests/unit/indexed/services/`** | misplaced core service tests | **MERGE → indexed_core/** | Mirror drift | Quick win |
| **`indexed-parsing`** | `packages/indexed-parsing/` | **KEEP** | Clean layer; survives v2 | — |
| **`indexed-config`** | `packages/indexed-config/` | **KEEP** | Surviving infra; slim merge paths | — |
| **`utils`** (slimmed) | `packages/utils/` | **KEEP** | Shared foundation after relocations | — |
| **CLI + MCP app shell** | `apps/indexed/` | **KEEP structure, MERGE internals** | Correct top layer | Ongoing / #119 |
| **`ParsingModule` facade** | `parsing/__init__.py` | **KEEP** | Right abstraction | — |
| **`v1_adapter`** | `connectors/files/v1_adapter.py` | **KEEP until v2** | Explicit v1 dict bridge | v2 |
| **`DocumentCacheReaderDecorator`** | `document_cache_reader_decorator.py` | **KEEP** | Used in create factory | v2 evaluate |
| **Legacy data migration** | `apps/indexed/utils/migration.py` | **KEEP short-term** | User-facing `./data` → `~/.indexed` | Post-v1.0 delete |
| **`core/v1` engine + services** | `packages/indexed-core/src/core/v1/` | **DEFER → replace v2** | Rewrite, don't refactor | v2 |
| **`indexed-connectors` v1** | `packages/indexed-connectors/` | **DEFER → rewrite v2** | After protocols extraction | v2 |
| **Confluence readers (3 impl)** | `confluence/confluence_document_reader.py`, etc. | **DEFER unify** | Jira unified; Confluence split | v2 connectors |
| **`create.py`, `config/cli.py`** | app commands | **DEFER split** | Issue #119; 967L / 1959L | Phase 4 |
| **Oversized service modules** | `inspect_service.py`, `search_service.py`, etc. | **DEFER split** | File size limits | v2 |
| **`CoreV1IndexingConfig` unwired** | `config_models.py` | **DEFER wire OR DELETE** | Config UI-only; engine ignores | v2 |
| **Import-time config registration** | `core/v1/__init__.py`, connector inits | **DELETE pattern** | Explicit app bootstrap | Phase 1 |
| **`.spec/lessons.md`** | missing | **RESTORE** | AGENTS session-start required | Quick doc |
| **v2 feature spec folder** | `.spec/features/core-v2/` | **CREATE** | Plan routing before impl | Phase 2 kickoff |

---

## Architecture Target (v2)

```text
┌─────────────────────────────────────────┐
│  apps/indexed (CLI/MCP)                 │  composition root: bootstrap, registries, thin UI
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  indexed-core/v2                        │  engine + orchestration; NO connector imports
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  indexed-connectors/v2                  │  plugins implementing protocols only
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  indexed-protocols                      │  BaseConnector, DTOs, shared contracts
│  + indexed-config + indexed-parsing + utils │
└─────────────────────────────────────────┘
```

---

## Spec Alignment Scorecard

| Requirement (`.spec/`) | Status | Severity |
|------------------------|--------|----------|
| Dependencies flow downward only | **Violated** — core → connectors | P0 |
| Core receives connectors via DI | **Violated** — `_build_connector_from_config` switch | P0 |
| Explicit config registration at app init | **Violated** — import-time in core/connectors | P1 |
| No dual code paths (singleton + DI) | **Violated** — ConfigService, connector paths | P1 |
| CLI commands ≤150 lines | **Violated** — 10+ files over limit | P1 |
| MCP reuses same services as CLI | **Partial** — services yes, storage path no | P0 |
| Single-source config (no merge) | **Partial** — `load_raw()` OK, `read()` merges | P1 |
| `IndexedError` hierarchy | **Defined, unused** at boundaries | P1 |
| Lazy ML imports | **Mostly compliant** | OK |
| Feature 10 thin commands (#119) | **Open** | P1 |
| v2 rewrite (plan current focus) | **Not started** — no `core/v2/` | P2 |

---

## Quick Wins (Days, Low Risk)

1. Delete `FaissAutoIndexer` and auto indexer registry entries.
2. Remove deprecated converter/reader wrapper files; wire unified classes.
3. Route `remove.py` through `clear()` service; drop `Index` class.
4. Move `tests/unit/indexed/services/` → `tests/unit/indexed_core/`.
5. Add transient-only predicate to retry; fix sync connector retry behavior.
6. Delete `safe_getattr`, `PathsConfig`, `DOCLING_FALLBACK`.
7. Restore `.spec/lessons.md`.
