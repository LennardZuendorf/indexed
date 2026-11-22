---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# FAISS Indexing

## Index types

| Type | Use Case | Memory | Speed |
|------|----------|--------|-------|
| **IndexFlatL2** | <50K docs (default) | high | fast |
| IndexIVFFlat | 50K–1M docs | low | medium |
| IndexHNSW | >1M docs | medium | fast |

**Current:** only `IndexFlatL2` (exact similarity).

## Creation

**File:** `src/indexed/core/v1/engine/indexes/indexers/faiss_indexer.py`

```python
import faiss, numpy as np
index = faiss.IndexFlatL2(384)                       # 384 = all-MiniLM-L6-v2
index.add(np.array(embedding_list).astype('float32'))
distances, indices = index.search(query_vec, k=10)
```

## Similarity scoring

Embeddings are unit-normalized, so `IndexFlatL2` returns **squared** L2 distance
in **[0, 4]** — used directly as the result `score`, **lower means more similar**
(monotonic with cosine; not normalized to 0–1). Threshold filtering
(`min_score` / `score_threshold`) keeps chunks whose score is **≤** the threshold;
the configurable range is **[0, 4]** (a sane cutoff is >1.0), not [0, 1].
