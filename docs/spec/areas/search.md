---
type: area
updated: 2026-11-22
code: [src/indexed/core]
---

# Search

| Feature | Status | Description |
|---------|--------|-------------|
| **Semantic Search** | ✅ Shipped | Natural language queries via vector similarity |
| **Cross-Collection** | ✅ Shipped | Search across all collections simultaneously |
| **Single Collection** | ✅ Shipped | Target specific collection for focused results |
| **Relevance Scoring** | ✅ Shipped | FAISS squared-L2 ranking (lower = closer match) |
| **Result Limits** | ✅ Shipped | Configurable max results per query |
| **Multiple Formats** | ✅ Shipped | Table, card, compact, JSON output |
| **Reranking (v2)** | ✅ Shipped | `--rerank`/`--no-rerank` — cross-encoder rerank, v2 collections only |
| Filters | 📋 Planned | Filter by date, source type, metadata |
| Boolean Operators | 📋 Planned | AND, OR, NOT query composition |
| Phrase Search | 📋 Planned | Exact phrase matching |
