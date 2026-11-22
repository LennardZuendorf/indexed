---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Performance

## Search latency

**Target:** <1s for 10K–100K docs. **Actual:** ~800ms (10K), ~1.5s (100K).

Optimizations: searcher caching (reuse loaded FAISS indexes), memory-mapped indexes,
batch query embedding.

## Memory

Idle ~80MB; indexing ~400MB; search ~250MB (embedding model + index).
**Ordering: parsing needs a tokenizer before this acquisition runs.** On a clean
install `index create` parses (and chunk-counts) every document before the
embedder downloads the repository, so parsing fetches the tokenizer alone on a
cache miss and caches that outcome — see [tech/parsing](../parsing/README.md) § Token window &
tokenizer acquisition. `indexed init` runs this whole acquisition up front
(weights + tokenizer), so nothing after it needs the network.
