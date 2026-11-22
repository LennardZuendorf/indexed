---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Batching

`embed_batch` defaults to `DEFAULT_EMBEDDING_BATCH_SIZE = 128` (configurable per call).

## Chunk-size invariant

Every chunk must tokenize to **≤ the embedder's `max_seq_length`** (256 for the
default `all-MiniLM-L6-v2`), read live from the embedder — never a hardcoded 512.
Oversized text is split down to the token window (see [tech/parsing](../parsing/README.md))
so no content is silently truncated at embed time.
