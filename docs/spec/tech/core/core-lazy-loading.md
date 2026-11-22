---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Lazy loading

**File:** `src/indexed/core/v1/engine/indexes/embeddings/sentence_embeder.py`

`SentenceEmbedder` exposes the model via a lazy `@property` — the heavy model is
loaded (and cached) on first access, not at import:

```python
@property
def model(self):
    """Lazy-load the embedding model on first access."""
    return get_embedding_model(self.model_name)
```
