---
type: branch
scope: core
parent: tech.md
covers: engine components, embedding strategy, FAISS indexing, persistence, search performance
updated: 2026-10-25
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
by model, never by `dict["stringKey"]`, so a field rename is a ty error rather than a
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

### Model cache contract

**Files:** `src/indexed/core/v1/engine/indexes/embeddings/model_manager.py`,
`src/indexed/core/v2/embedding/local.py`, `src/indexed/core/model_acquisition.py`

The embedding model lives in the shared HF hub cache (`HF_HUB_CACHE` >
`HF_HOME/hub` > `~/.cache/huggingface/hub`, `models--<org>--<name>/snapshots/<rev>/`).
A model counts as **cached** only when a snapshot holds a real weights file
(`model.safetensors` / `pytorch_model.bin`, resolving to a completed blob) — hub
symlinks a snapshot file only once its blob completes, so an interrupted download
leaves config/tokenizer files WITHOUT weights, and a weights-blind "any file"
check would pin the load offline (`local_files_only=True`) and then fail on the
missing weights — one interrupted download bricks every embedding op until a
manual re-download. v1 (`is_model_cached`) and core.v2 (`_is_model_cached`)
carry identical semantics (a parity test keeps them in lockstep).

**Predicate and loader are one selection.** v1's `_select_cached_snapshot` is the
single source for both `is_model_cached` and `_resolve_snapshot_path`, and
`load_model` loads THAT snapshot path (not the repo id) with
`local_files_only=True` — so "cached" always means "loadable offline" and a
config-only residue can never be reported as a false cached success. refs/main
names the active revision; with none, the first weights-bearing snapshot wins.

### Acquisition failure surface (issue #210)

**File:** `src/indexed/core/model_acquisition.py`

Acquisition (download/load) is bounded and categorized so an impossible
acquisition fails predictably instead of leaking dependency retry chatter:

- `acquire_with_retry` retries only transient failures (network / HTTP 429) up
  to `MAX_ATTEMPTS = 3` with exponential backoff; permanent failures (missing
  repo, 401/403/gated) raise immediately. Every retry logs at DEBUG, so
  `--debug` keeps the timeline while the default surface shows one line.
- The final failure is wrapped in `ModelAcquisitionError` (an `IndexedError`) —
  model name, cache dir + state, failure category, and a category-specific
  remedy (`indexed init --model …` / `--force` / network / auth). Token-shaped
  secrets are redacted from any cause text.
- `huggingface_hub`'s per-retry WARNINGs are floored at ERROR in
  `utils/logger.py`; `--debug` lowers them back to DEBUG. transformers' "does
  not appear to have a file named pytorch_model.bin or model.safetensors" fires
  for ANY swallowed lookup (offline, unreachable hub, gated, or genuinely
  absent) and must never surface raw.
- `ensure_model` verifies the download left weights; a "successful" weightless
  call raises rather than reporting a cached success. `--force` create no longer
  clears the existing collection up front — the build-aside/rename-swap keeps a
  failed acquisition from clobbering a healthy index.

### Collection replace + interrupted-swap recovery (#126)

**Files:** `src/indexed/core/v2/persist.py` (`replace_dir`),
`src/indexed/core/v2/ingestion.py` (create/update call sites),
`src/indexed/core/recovery.py`, `src/indexed/core/engine.py` (`_recover` gates).

A collection is never mutated in place: the new generation is built beside the
live directory and swapped in with two renames — `rename(dest -> dest.trash-<pid>)`
then `rename(<name>.tmp-<pid>-<hex> -> dest)` — after which the trash is removed.
A failure of the second rename renames the original back and re-raises.

The remaining window is a CRASH between those two renames: the canonical path is
missing while both generations sit in directories discovery excludes
(`\.(?:tmp|trash)-\d+`). `core.recovery.recover_stranded` therefore runs inside
every list/open gate (`_existing_collection_names`, `_resolve_existing_engine`,
`_group_names_by_engine`, `discover_v2_collections`) and:

- restores the newest COMPLETE generation (readable `version: "2"` manifest plus
  all three `storage/*.json` files) to the canonical name when a `.trash-`
  sibling proves the swap was in flight;
- never promotes a `.tmp-`-only strand (an interrupted new build was never
  published) and never mixes two generations;
- quarantines anything it cannot prove restorable into `<collections>/.recovery/<name>/`
  — moved, never deleted — with a `recovery.log` for the operator;
- removes a `.trash-` sibling only when the canonical directory is already
  complete (finishing the interrupted cleanup);
- skips a strand whose pid is still alive (a concurrent builder);
- raises `CollectionRecoveryError` for an EXPLICITLY requested collection that
  could not be restored, so it never reads as "no such collection".

**Contract:** recoverable after a process crash between the renames. NOT
power-loss safe — there is no `fsync` in the rename chain, so unflushed pages
after a power cut are outside this guarantee.

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
