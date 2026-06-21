---
type: branch
scope: core
parent: tech.md
covers: engine components, embedding strategy, FAISS indexing, persistence, search performance
updated: 2026-06-21
---

# Tech Branch: Core Engine (`indexed-core`)

Indexing & search engine. Receives connectors via dependency injection; never
imports concrete connectors, CLI, or MCP (see [tech.md](tech.md) § Architectural Rules).

**Parent: [tech.md](tech.md).** Pipelines (cross-component): [tech.md](tech.md) § Data Flow.

> **Upcoming:** [Issue #5 — Core v2: LlamaIndex Engine Rebuild](https://github.com/LennardZuendorf/indexed/issues/5)
> New `core/v2/` namespace using LlamaIndex as the engine layer (pluggable vector
> stores, standard document/node model). `core/v1/` stays until v2 is stable.
> Feature spec lives under `.spec/features/` when the branch starts.

---

## Engine Components

| Component | Role |
|-----------|------|
| **DocumentCollectionCreator** | Orchestrates read → convert → chunk → embed → index → persist |
| **DocumentCollectionSearcher** | Loads index + maps results; cached across queries |
| **FaissIndexer** | Vector storage + similarity search |
| **SentenceEmbedder** | Embedding generation (lazy-loaded) |
| **DiskPersister** | Atomic disk persistence |

---

## Embedding Strategy

**Default:** `all-MiniLM-L6-v2` — 384-dim, ~22MB, fast, good general quality.
**Alternatives:** `all-mpnet-base-v2` (768-dim, higher quality), `multi-qa-distilbert-cos-v1` (768-dim, Q&A).

### Lazy loading

**File:** `packages/indexed-core/src/core/v1/engine/indexes/embeddings/sentence_embeder.py`

`SentenceEmbedder` exposes the model via a lazy `@property` — the heavy model is
loaded (and cached) on first access, not at import:

```python
@property
def model(self):
    """Lazy-load the embedding model on first access."""
    return get_embedding_model(self.model_name)
```

### Batching

`embed_batch` defaults to `DEFAULT_EMBEDDING_BATCH_SIZE = 128`, but both indexers
call it with `batch_size=64`, so the effective indexing batch is 64.

---

## FAISS Indexing

### Index types

`FaissIndexer` (default) is always `IndexFlatL2`. `FaissAutoIndexer` (opt-in)
auto-selects by vector count:

| Vectors | Index | Notes |
|---------|-------|-------|
| <10K | **IndexFlatL2** | exact |
| 10K–1M | IndexHNSWFlat (M=32) | approximate; efConstruction=200, efSearch=128 |
| >1M | IndexIVFPQ | approximate, memory-efficient (nlist≤4096, m=16, nbits=8) |

**Default stays `IndexFlatL2`** (`constants.py` `DEFAULT_INDEXER`); auto-selection
is opt-in via the `indexer_FAISS_Auto__*` registry name. Both wrap the index in
`faiss.IndexIDMap` and add vectors with `add_with_ids`.

### Creation

**File:** `packages/indexed-core/src/core/v1/engine/indexes/indexers/faiss_indexer.py`

```python
import faiss, numpy as np
dim = embedder.get_number_of_dimensions()           # 384 for all-MiniLM-L6-v2
index = faiss.IndexIDMap(faiss.IndexFlatL2(dim))     # default indexer
index.add_with_ids(embeddings, np.array(ids, dtype=np.int64))
distances, indices = index.search(query_vec, number_of_results)
```

Persistence uses native `faiss.write_index` / `read_index` (memory-mapped), or
`serialize_index` / `deserialize_index`.

### Similarity scoring

FAISS returns L2 distances. The raw distance is used directly as the result
`score` — **lower means more similar** (it is not normalized to 0–1). Threshold
filtering (`score_threshold`, default `None`) keeps chunks whose score (distance)
is **≤** the threshold.

---

## Persistence Strategy

`DiskPersister` atomic writes: write temp file → `fsync()` → rename (atomic on POSIX).
Prevents corruption from process/system crashes and disk-full errors.

On-disk layout (dirs owned by `indexed-config`): [tech-config.md](tech-config.md) § Storage Directory Structure.

---

## Performance

### Search latency

**Target:** <1s for 10K–100K docs. **Actual:** ~800ms (10K), ~1.5s (100K).

Optimizations: searcher caching (reuse loaded FAISS indexes), memory-mapped indexes,
batch query embedding.

### Memory

Idle ~80MB; indexing ~400MB; search ~250MB (embedding model + index).
