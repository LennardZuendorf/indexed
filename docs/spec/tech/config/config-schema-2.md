---
type: tech
updated: 2026-11-22
applies: "src/indexed/config/**"
---

# Config Schema (2)

> **Note:** `[core.v1.indexing]` (`chunk_size`/`chunk_overlap`) and most of
> `[core.v1.embedding]` are currently **registered but unread** — effective
> chunking uses the embedder's token window ([Chunk-size invariant](../core/core-batching-chunk-size.md)), not `chunk_size`. Only `embedding.batch_size` and
> `[core.v1.search]` are wired today. Tracked for wiring/removal in a later
> config pass.
