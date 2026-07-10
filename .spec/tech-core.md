---
type: branch
scope: core
parent: tech.md
covers: engine components, embedding strategy, FAISS indexing, persistence, search performance
updated: 2026-07-10
---

# Tech Branch: Core Engine (`src/indexed/core/`)

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

## Typed Data Contracts

The three on-disk shapes the engine moves — the collection **manifest**, each
**converted document + chunk**, and each per-collection **search result** — are typed
Pydantic models in the `protocols` leaf (`protocols/models.py`: `Manifest`,
`ConvertedDocument`, `Chunk`, `CollectionSearchResult`). The engine reads and writes them
by model, never by `dict["stringKey"]`, so a field rename is a mypy error rather than a
runtime `KeyError`. `model_dump(by_alias=True, exclude_none=True)` reproduces today's
camelCase JSON **byte-stable** — the on-disk v1 format is the compatibility boundary for
the v2 core swap. Full contract: [tech.md](tech.md) § Protocols Package.

---

## Embedding Strategy

**Default:** `all-MiniLM-L6-v2` — 384-dim, ~22MB, fast, good general quality.
**Alternatives:** `all-mpnet-base-v2` (768-dim, higher quality), `multi-qa-distilbert-cos-v1` (768-dim, Q&A).

### Lazy loading

**File:** `src/indexed/core/v1/engine/indexes/embeddings/sentence_embeder.py`

`SentenceEmbedder` exposes the model via a lazy `@property` — the heavy model is
loaded (and cached) on first access, not at import:

```python
@property
def model(self):
    """Lazy-load the embedding model on first access."""
    return get_embedding_model(self.model_name)
```

### Batching

`embed_batch` defaults to `DEFAULT_EMBEDDING_BATCH_SIZE = 128` (configurable per call).

### Chunk-size invariant

Every chunk must tokenize to **≤ the embedder's `max_seq_length`** (256 for the
default `all-MiniLM-L6-v2`), read live from the embedder — never a hardcoded 512.
Oversized text is split down to the token window (see [tech-parsing.md](tech-parsing.md))
so no content is silently truncated at embed time.

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

**File:** `src/indexed/core/v1/engine/indexes/indexers/faiss_indexer.py`

```python
import faiss, numpy as np
index = faiss.IndexFlatL2(384)                       # 384 = all-MiniLM-L6-v2
index.add(np.array(embedding_list).astype('float32'))
distances, indices = index.search(query_vec, k=10)
```

### Similarity scoring

Embeddings are unit-normalized, so `IndexFlatL2` returns **squared** L2 distance
in **[0, 4]** — used directly as the result `score`, **lower means more similar**
(monotonic with cosine; not normalized to 0–1). Threshold filtering
(`min_score` / `score_threshold`) keeps chunks whose score is **≤** the threshold;
the configurable range is **[0, 4]** (a sane cutoff is >1.0), not [0, 1].

---

## Persistence Strategy

`DiskPersister` atomic writes: write temp file → `fsync()` → rename (atomic on POSIX).
Prevents corruption from process/system crashes and disk-full errors.

**Durability invariants:**
- The FAISS index is persisted on **every** mutating path — create, add,
  remove-then-add, deletions-only, and explicit-deletions — so on-disk vectors
  never outlive their mapping keys (no orphaned ids / `KeyError` on later search).
- A failed `create` **builds aside and rename-swaps** into place, so an error
  mid-run never destroys the prior collection of the same name.
- A zero-chunk batch (e.g. an empty-body document) is a **no-op**, not a crash.

On-disk layout (dirs owned by `src/indexed/config/`): [tech-config.md](tech-config.md) § Storage Directory Structure.

---

## Performance

### Search latency

**Target:** <1s for 10K–100K docs. **Actual:** ~800ms (10K), ~1.5s (100K).

Optimizations: searcher caching (reuse loaded FAISS indexes), memory-mapped indexes,
batch query embedding.

### Memory

Idle ~80MB; indexing ~400MB; search ~250MB (embedding model + index).
