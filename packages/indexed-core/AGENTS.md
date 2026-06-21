# indexed-core — Engine (indexing & search)

> Scope: this package. Workflow, rules, and verify gate live in the root
> [`AGENTS.md`](../../AGENTS.md). Canonical design: [`.spec/tech-core.md`](../../.spec/tech-core.md).

## What this is

The indexing & search engine, plus the connector **protocols** and service layer.
Receives connectors via **dependency injection** — it never imports concrete
connectors, CLI, or MCP.

## Layer & dependencies

Business-logic layer. May import: protocols (defined here), `indexed_config`,
`utils`. MUST NOT import: CLI, MCP, or concrete connector implementations.

## Where to find what

```
src/core/v1/
  index.py                       Index facade (public Python API)
  config_models.py constants.py  typed config · DEFAULT_EMBEDDING_BATCH_SIZE etc.
  connectors/base.py metadata.py DocumentReader / DocumentConverter / BaseConnector protocols
  engine/
    core/
      documents_collection_creator.py   orchestrates read→convert→chunk→embed→index→persist
      documents_collection_searcher.py  loads index + maps results; cached across queries
    factories/                          create · search · update collection factories
    indexes/
      embeddings/  sentence_embeder.py (lazy @property model), model_manager, _model_cache
      indexers/    faiss_indexer.py (IndexFlatL2), faiss_auto_indexer.py
      indexer_factory.py indexer_registry.py
    persisters/disk_persister.py        atomic write (tmp → fsync → rename)
    services/    collection_service · search_service · inspect_service · models
```

## Architecture notes

- **Embeddings:** default `all-MiniLM-L6-v2` (384-dim). The model is a lazy
  `@property` — loaded/cached on first access, **never at import**. `embed_batch`
  default batch size 128.
- **FAISS:** only `IndexFlatL2` today (exact L2). Correct for <50k docs. Score is
  the raw L2 **distance — lower is more similar**, not normalized; `min_score`
  filters keep score ≤ threshold.
- **Searcher caching:** loaded FAISS indexes are reused across queries — the main
  search-latency optimization (target <1s for 10k–100k docs).
- **Persistence:** `DiskPersister` writes atomically; on-disk layout is owned by
  `indexed-config` ([`.spec/tech-config.md`](../../.spec/tech-config.md)).
- All exceptions inherit `IndexedError`. Service modules ≤300 lines.
