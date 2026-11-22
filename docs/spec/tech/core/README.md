---
type: hub
updated: 2026-11-22
---

# Core tech spec

Engine components, embedding, FAISS, persistence, git awareness, freshness, performance (src/indexed/core).

- [Core engine overview](core-overview.md)
- [Engine Components](core-engine-components.md)
- [Typed Data Contracts](core-typed-data-contracts.md)
- [Embedding Strategy](core-embedding-strategy.md)
- [Lazy loading](core-lazy-loading.md)
- [Model cache contract](core-model-cache-contract.md)
- [Model cache contract: The filter is bandwidth](core-model-cache-contract-the-filter-is-bandwidth.md)
- [Acquisition failure surface (issue #210)](core-acquisition-failure-surface.md)
- [Collection replace + interrupted-swap recovery (#126)](core-collection-replace-recovery.md)
- [Batching](core-batching-chunk-size.md)
- [FAISS Indexing](core-faiss-indexing.md)
- [Search-Time Git Awareness (v2, issues #60/#144/#146)](core-search-time-git-awareness.md)
- [Search-Time Git Awareness (v2, issues #60/#144/#146): Git-signal re-rank](core-search-time-git-awareness-git-signal-re-rank.md)
- [Search-Time Git Awareness (v2, issues #60/#144/#146): Provenance never outlives its snapshot](core-search-time-git-awareness-provenance-never-outlives-its.md)
- [Index Freshness (files collections, #146 slice 1)](core-index-freshness.md)
- [Persistence Strategy](core-persistence-strategy.md)
- [Performance](core-performance.md)
