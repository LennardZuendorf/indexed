---
type: branch
scope: core
parent: tech.md
covers: engine components, embedding strategy, FAISS indexing, persistence, search performance
updated: 2026-06-09
---

# Tech Branch: Core Engine (`indexed-core`)

Indexing & search engine. Receives connectors via dependency injection; never
imports concrete connectors, CLI, or MCP (see [tech.md](tech.md) § Architectural Rules).

**Parent: [tech.md](tech.md).** Pipelines (cross-component): [tech.md](tech.md) § Data Flow.

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

**File:** `packages/indexed-core/src/core/v1/engine/indexes/embeddings/sentence_embedder.py`

```python
def get_embedder():
    """Lazy load to avoid 500ms+ import cost at CLI startup."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)
```

### Batching

Batch size 32 (configurable). ~120 docs/min on M1 MacBook Pro.

---

## FAISS Indexing

### Index types

| Type | Use Case | Memory | Speed |
|------|----------|--------|-------|
| **IndexFlatL2** | <50K docs (default) | high | fast |
| IndexIVFFlat | 50K–1M docs | low | medium |
| IndexHNSW | >1M docs | medium | fast |

**Current:** only `IndexFlatL2` (exact similarity).

### Creation

**File:** `packages/indexed-core/src/core/v1/engine/indexes/faiss_indexer.py`

```python
import faiss, numpy as np
index = faiss.IndexFlatL2(384)                       # 384 = all-MiniLM-L6-v2
index.add(np.array(embedding_list).astype('float32'))
distances, indices = index.search(query_vec, k=10)
```

### Similarity scoring

FAISS returns L2 distances (lower = more similar). Score: `1 / (1 + distance)`.

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
