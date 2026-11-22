---
type: tech
updated: 2026-11-22
applies: ["src/indexed/core/**", "src/indexed/connectors/**", "src/indexed/parsing/**"]
---

# Data Flow

Cross-component pipelines. Component internals: [tech/core](core/README.md),
[tech/connectors](connectors/README.md), [tech/parsing](parsing/README.md).

## Indexing Pipeline

```text
Source API → Reader → Converter → Chunker → Embedder → Indexer → Persister
```

1. **Reader** fetches documents from source (Jira API, file system, etc.)
2. **Converter** transforms to standardized `Document` objects
3. **Chunker** splits into token-window chunks (≤ embedder `max_seq_length`, 256 for the default model — never silently truncated; see [tech/parsing](parsing/README.md))
4. **Embedder** generates vectors (384-dim via `all-MiniLM-L6-v2`)
5. **Indexer** builds FAISS index (`IndexFlatL2` default)
6. **Persister** saves to disk atomically

## Search Pipeline

```text
Query → Embedder → FAISS Search → Result Mapper → Formatter
```

1. **Embedder** converts query text to vector (same model as indexing)
2. **FAISS Search** finds K nearest neighbors (squared L2 distance in [0, 4]; lower = closer)
3. **Result Mapper** looks up chunks, documents, metadata
4. **Formatter** outputs as card/table/compact/JSON
