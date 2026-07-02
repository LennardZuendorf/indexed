---
type: feature-research
feature: architecture-audit
cluster: core
parent: ../product.md
updated: 2026-06-29
---

# Research: indexed-core

Discovery artifact from the 2026-06-29 monorepo architecture audit. Covers
`packages/indexed-core/` (~4,113 LOC, 27 modules, v1 only — no v2 scaffold).

**Related:** [product.md](../product.md) R1 (downward-only graph), R2 (protocols
in lowest package). [tech-core.md](../../../tech-core.md) § Engine Components.

---

## Summary

`indexed-core` is the indexing and search engine and remains **surviving v0.1
infra**, but it violates its own layer contract: three modules import concrete
connectors, and the engine layer imports service DTOs upward from
`engine/services/models.py`. The package is v1-only (~4,100 LOC across 27 files)
with no v2 scaffold; two god modules (`documents_collection_creator` 507L,
`inspect_service` 431L) exceed the 400L module cap, and a third
(`update_collection_factory` 417L) is borderline. Speculative code (`FaissAutoIndexer`,
unused `Index` facade, dead `SearchResult` DTO) and a triple API surface (class +
singleton + DTOs) add maintenance cost without product payoff at current scale.

---

## Current Architecture

```
packages/indexed-core/src/core/
  __init__.py
  v1/
    index.py                         Index facade (279L) — thin wrapper over services
    config_models.py constants.py    paths, batch sizes
    connectors/
      base.py metadata.py            DocumentReader / DocumentConverter / BaseConnector protocols
    engine/
      core/
        documents_collection_creator.py   read→convert→chunk→embed→index→persist (507L)
        documents_collection_searcher.py    load FAISS + map results; cached
      factories/
        create_collection_factory.py      wires reader/converter/indexer/persister
        update_collection_factory.py      incremental update + registry lookup (417L)
        search_collection_factory.py
      indexes/
        embeddings/                       lazy SentenceEmbedder, model cache
        indexers/                         FaissIndexer, FaissAutoIndexer (YAGNI)
        indexer_factory.py indexer_registry.py
      persisters/disk_persister.py
      services/
        collection_service.py             create/update/clear + connector wiring (342L)
        search_service.py                 SearchService + search() singleton (376L)
        inspect_service.py                InspectService + status/inspect singleton (431L)
        models.py                         SourceConfig, CollectionInfo, dead SearchResult
```

**Intended flow:** CLI/MCP → service functions → factories →
`DocumentCollectionCreator` / `DocumentCollectionSearcher` → FAISS + DiskPersister.

**Actual coupling leaks:**

| Layer violation | Where |
|-----------------|-------|
| Core → connectors | `collection_service._build_connector_from_config`, `create_collection_factory`, `update_collection_factory` |
| Engine → services | `documents_collection_creator` imports `ProgressUpdate`, `PhasedProgressCallback` from `engine/services/models` |
| App bypasses Index | Primary CLI/MCP path calls `create`/`search`/`status` directly; `Index` used only in `search.py` and `remove.py` |

**Dual connector wiring:** `collection_service` hard-codes per-type `if/elif` +
lazy imports alongside `update_collection_factory` registry-based
(`get_connector_class`, `get_config_namespace`) path — two resolution strategies
for the same job.

---

## Spec Compliance Gaps

| Finding | Priority | Path |
|---------|----------|------|
| Core imports concrete connectors (violates R1 + tech-core § Layer) | **P0** | `engine/services/collection_service.py:38–106`, `engine/factories/create_collection_factory.py:3`, `engine/factories/update_collection_factory.py:155,375–376` |
| Engine imports from services/models (inverted dependency) | **P1** | `engine/core/documents_collection_creator.py:28` → `engine/services/models.py` |
| Service modules exceed 300L cap | **P1** | `inspect_service.py` (431L), `search_service.py` (376L), `collection_service.py` (342L) |
| Engine modules exceed 400L cap | **P1** | `documents_collection_creator.py` (507L), `update_collection_factory.py` (417L) |
| `FaissAutoIndexer` (HNSW/IVFPQ) unused at product scale; spec says IndexFlatL2 only | **P2** | `engine/indexes/indexers/faiss_auto_indexer.py`, `indexer_factory.py:38–101` |
| `Index` facade documented as public API but bypassed by main CLI/MCP | **P2** | `v1/index.py`; callers in `apps/indexed/.../search.py`, `remove.py` only |
| `SearchResult` DTO exported, never consumed | **P2** | `engine/services/models.py:99`, `services/__init__.py` |
| Protocols live in core (blocks R2 lowest-package extraction) | **P1** | `v1/connectors/base.py`, `metadata.py` |
| Circular-import workaround via lazy import | **P2** | `collection_service.py:16–17` comment re `update_collection_factory` |

---

## DRY/KISS Violations

1. **Dual connector resolution** — `collection_service._build_connector_from_config`
   duplicates registry knowledge already in `connectors/registry.py` and
   `update_collection_factory`.
2. **Triple API surface** — `Index` class, module-level singletons (`search()`,
   `status()`, `inspect()`), and overlapping DTOs (`SourceConfig` vs connector
   config schemas vs manifest shapes).
3. **Progress types in wrong layer** — `PhasedProgressCallback` / `ProgressUpdate`
   belong in a shared protocols or app layer, not `engine/services/models` imported
   back into the engine.
4. **FaissAutoIndexer complexity** — three index types (FlatL2, HNSW, IVFPQ) for
   collections that today never exceed the FlatL2 threshold (<50k docs per spec).
5. **Singleton services** — `_default_service` globals in `search_service` and
   `inspect_service` mirror the config singleton anti-pattern; state persists
   across CLI invocations within a process.
6. **Duplicate connector namespace mapping** — unified `sources.jira` /
   `sources.confluence` logic appears in both `collection_service` and
   `connectors/registry.NAMESPACE_REGISTRY`.

---

## Refactoring Opportunities

### P0 — Remove core → connectors imports (R1)

1. Delete `_build_connector_from_config` from core; move connector instantiation
   to app composition root (`apps/indexed/app.py` or dedicated bootstrap).
2. Pass `DocumentReader` + `DocumentConverter` (or `BaseConnector`) into
   `create()` / `update()` — core receives protocols only.
3. Remove top-level `from connectors...` in `create_collection_factory`; accept
   optional cache decorator injection from app layer.
4. Add CI import-graph gate: `indexed-core` MUST NOT depend on `indexed-connectors`.

### P1 — Extract protocols + progress types (R2)

1. Move `base.py`, `metadata.py`, and presentation-agnostic DTOs to
   `indexed-protocols` (or equivalent lowest package).
2. Move `ProgressUpdate`, `PhasedProgressCallback`, `ProgressCallback` out of
   `engine/services/models` into protocols or app layer.
3. Keep engine-only types (`CollectionStatus` internals) in core if needed.

### P1 — Split god modules

| Module | Split target |
|--------|--------------|
| `documents_collection_creator.py` (507L) | Pipeline orchestrator + phase runners (read, embed, persist) |
| `inspect_service.py` (431L) | Manifest reader + formatter; shrink service to ≤300L |
| `update_collection_factory.py` (417L) | Diff/merge logic vs factory wiring |

### P2 — Collapse API surface

1. Pick **one** public entry: functional services (`create`, `search`, `status`)
   for CLI/MCP; demote or remove `Index` facade unless library API is product goal.
2. Delete `SearchResult` or wire it through search pipeline.
3. Remove `SearchService` / `InspectService` class + singleton duplication — keep
   either class or functions, not both.

### P2 — Delete speculative indexing

Remove `FaissAutoIndexer` and registry entries; keep `FaissIndexer` (IndexFlatL2)
until v2 justifies approximate indexes.

---

## Delete vs Keep vs Defer

| Component | Path(s) | Action | Rationale | When |
|-----------|---------|--------|-----------|------|
| `_build_connector_from_config` | `collection_service.py` | **DELETE** | Violates R1; belongs in app | Phase 1 |
| Top-level connectors import | `create_collection_factory.py` | **DELETE** | Inject cache decorator | Phase 1 |
| Registry imports in factory | `update_collection_factory.py` | **MOVE → app** | Core must not resolve types | Phase 1 |
| `FaissAutoIndexer` | `faiss_auto_indexer.py`, `indexer_factory.py` | **DELETE** | YAGNI; untested at scale | Quick win |
| `SearchResult` DTO | `models.py` | **DELETE** | Zero consumers | Quick win |
| `Index` facade | `v1/index.py` | **DEFER** | 2 CLI commands still use it; migrate first | Phase 1–2 |
| `SearchService` / `InspectService` classes | `*_service.py` | **MERGE** | Collapse to functions or classes, not both | Phase 2 |
| `DocumentCollectionCreator` | `engine/core/` | **KEEP** (split) | Core orchestration — correct home | — |
| `DocumentCollectionSearcher` | `engine/core/` | **KEEP** | Search cache is key perf path | — |
| `FaissIndexer` | `faiss_indexer.py` | **KEEP** | Matches spec (FlatL2) | — |
| `DiskPersister` | `disk_persister.py` | **KEEP** | Atomic persistence works | — |
| Protocols in core | `v1/connectors/` | **MOVE → protocols pkg** | R2 prerequisite | Phase 1 |
| `core/v2/` scaffold | (none) | **DEFER** | No v2 tree exists; create with feature spec | v2 kickoff |

---

## Essential Files

- `engine/core/documents_collection_creator.py` — index pipeline orchestrator (split target)
- `engine/core/documents_collection_searcher.py` — FAISS load + result mapping
- `engine/factories/create_collection_factory.py` — creator wiring
- `engine/factories/update_collection_factory.py` — incremental update (move connector lookup out)
- `engine/factories/search_collection_factory.py` — searcher factory
- `engine/indexes/indexers/faiss_indexer.py` — vector index (keep)
- `engine/indexes/embeddings/sentence_embeder.py` — lazy embedding model
- `engine/indexes/indexer_factory.py` — indexer selection (simplify after AutoIndexer removal)
- `engine/persisters/disk_persister.py` — atomic disk writes
- `engine/services/collection_service.py` — create/update/clear (strip connector wiring)
- `engine/services/search_service.py` — search entry
- `engine/services/inspect_service.py` — status/inspect entry
- `engine/services/models.py` — `SourceConfig` + status DTOs (relocate progress types)
- `v1/connectors/base.py` — protocols (move to lowest package)
- `v1/connectors/metadata.py` — connector metadata (move with protocols)
- `v1/index.py` — Index facade (migrate callers, then delete or keep as library API)
- `v1/config_models.py` — default paths and typed config helpers
