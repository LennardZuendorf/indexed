# LlamaIndex FAISS Integration - Refactor Brief

**Date:** 2025-10-05  
**Status:** 🟡 In Progress  
**Priority:** High  
**Estimated Effort:** 2-4 hours

---

## 📋 Context

The V2 architecture uses a clean Controller/Service pattern with raw FAISS for vector storage. However, this approach stores text content separately from vectors (in `.mappings.pkl`), which prevents using LlamaIndex's query capabilities.

### Current Architecture (V2)
```
StorageService (packages/indexed-core/src/index/services/storage.py)
├─ Raw FAISS index (vectors only)
└─ chunk_metadata dict (text stored separately)
```

**Problem:** LlamaIndex cannot query this setup because it expects text to be embedded IN the vector store as `TextNode` objects.

---

## 🎯 Goal

Refactor the V2 `StorageService` to use **LlamaIndex's `FaissVectorStore`** instead of raw FAISS, enabling:

1. ✅ Proper semantic search with LlamaIndex query interface
2. ✅ Text content stored correctly in vector store
3. ✅ Future extensibility for RAG/advanced features
4. ✅ Maintain V2 architecture patterns (Controller/Service)
5. ✅ Keep smart embedding selection (cloud for queries, local for indexing)

---

## 📦 What's Already Done

### ✅ Smart Embedding Selection
**File:** `packages/indexed-core/src/index/services/search.py`

```python
# Automatically detects HUGGINGFACE_API_TOKEN
# Uses cloud embeddings for queries (instant ~1s)
# Falls back to local model if no token (~90s)
```

**Benefits:**
- CLI queries are instant when HF token is set
- No 90s model loading wait for queries
- Indexing still uses local embeddings (privacy, no cost)

### ✅ Faster Model Loading
**File:** `packages/indexed-core/src/index/services/embedding.py`

```python
# Added trust_remote_code=True to SentenceTransformer()
# First load: ~80s (normal)
# Subsequent loads: ~2-3s (cached)
```

### ✅ Dependencies Added
**File:** `packages/indexed-core/pyproject.toml`

```toml
"llama-index-core>=0.11.0",
"llama-index-vector-stores-faiss>=0.3.0",
```

---

## 🔨 What Needs to Be Done

### 1. Rewrite `StorageService` to use LlamaIndex

**File:** `packages/indexed-core/src/index/services/storage.py`

**Changes Required:**
```python
from llama_index.core.schema import TextNode
from llama_index.vector_stores.faiss import FaissVectorStore
from llama_index.core import StorageContext

class StorageService:
    def __init__(self, dimension, index_type, persistence_path):
        # Create raw FAISS index
        self.faiss_index = faiss.IndexFlatL2(dimension)
        
        # Wrap with LlamaIndex FaissVectorStore
        self.vector_store = FaissVectorStore(faiss_index=self.faiss_index)
        
        # Create storage context
        self.storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )
    
    def add_vectors(self, vectors, ids, metadata):
        # Create TextNode objects (LlamaIndex format)
        nodes = []
        for i, (chunk_id, embedding) in enumerate(zip(ids, vectors)):
            meta = metadata[i] if metadata else {}
            content = meta.get('content', '[No content]')
            
            node = TextNode(
                id_=chunk_id,
                text=content,  # ← TEXT STORED IN NODE!
                metadata=meta,
                embedding=embedding.tolist()
            )
            nodes.append(node)
        
        # Add to vector store
        self.vector_store.add(nodes)
    
    def search(self, query_vector, top_k):
        from llama_index.core.vector_stores.types import VectorStoreQuery
        
        query = VectorStoreQuery(
            query_embedding=query_vector.tolist(),
            similarity_top_k=top_k
        )
        
        result = self.vector_store.query(query)
        
        # Convert to existing format for compatibility
        return [
            (node.node_id, score, {**node.metadata, 'content': node.text})
            for node, score in zip(result.nodes, result.similarities)
        ]
```

**Key Points:**
- Maintain the same public API (add_vectors, search, save, load)
- Internal implementation uses LlamaIndex
- Existing code (IndexingService, SearchService) works unchanged

---

### 2. Update Persistence Logic

**Current:** Separate files
```
.indexed/
├── faiss_index          (FAISS vectors)
└── faiss_index.mappings.pkl  (text/metadata)
```

**New:** LlamaIndex format
```
.indexed/
├── faiss_index          (FAISS vectors)
└── faiss_index.docstore.json  (LlamaIndex docstore with text)
```

**Implementation:**
```python
def save(self):
    # Save FAISS index
    faiss.write_index(self.faiss_index, str(self.persistence_path))
    
    # Save docstore (LlamaIndex handles this)
    self.storage_context.persist(
        persist_dir=str(self.persistence_path.parent)
    )

def load(self):
    # Load FAISS index
    self.faiss_index = faiss.read_index(str(self.persistence_path))
    
    # Load docstore
    self.storage_context = StorageContext.from_defaults(
        persist_dir=str(self.persistence_path.parent)
    )
    
    # Recreate vector store
    self.vector_store = FaissVectorStore(faiss_index=self.faiss_index)
```

---

### 3. Enable LlamaIndex Queries (Optional)

**File:** `packages/indexed-core/src/index/services/llama_query.py` (currently empty)

This enables direct LlamaIndex queries with retrievers:

```python
class LlamaIndexQueryService:
    def __init__(self, storage_service, embedding_service):
        # Create VectorStoreIndex from storage service
        self.index = VectorStoreIndex.from_vector_store(
            vector_store=storage_service.vector_store,
            storage_context=storage_service.storage_context
        )
        
        # Create retriever
        self.retriever = VectorIndexRetriever(
            index=self.index,
            similarity_top_k=10
        )
    
    def query(self, query_text, top_k=10):
        # LlamaIndex handles embedding internally
        nodes = self.retriever.retrieve(query_text)
        
        # Convert to SearchResult format
        return [convert_node_to_search_result(node) for node in nodes]
```

**Integration in SearchService:**
```python
# SearchService.__init__
if self.query_embedding_service:  # Cloud embeddings available
    self.llama_query_service = LlamaIndexQueryService(
        storage_service, query_embedding_service
    )
```

---

## 🧪 Testing Plan

### Test 1: Re-index Documents
```bash
# Clear old index
rm -rf .indexed/

# Re-index with new LlamaIndex storage
uv run indexed-cli index files --path ./test-docs --engine v2

# Verify files created:
# - .indexed/faiss_index
# - .indexed/faiss_index.docstore.json (NEW!)
```

### Test 2: Search Works
```bash
# Without HF token (uses local embeddings - slow)
uv run indexed-cli index search "test query" --engine v2

# With HF token (uses cloud embeddings - fast)
export HUGGINGFACE_API_TOKEN=your_token
uv run indexed-cli index search "test query" --engine v2
```

### Test 3: Persistence Works
```bash
# Index once
uv run indexed-cli index files --path ./test-docs

# Search (should load from disk)
uv run indexed-cli index search "test"

# Should see "Loaded existing index with N vectors"
```

### Test 4: MCP Server Works
```bash
# Start MCP server (loads model once)
uv run indexed-mcp

# From Claude/client - make search requests
# Should be instant after initial load
```

---

## ⚠️ Breaking Changes

### User Impact
- **Existing indexes MUST be rebuilt** (format incompatible)
- Old `.mappings.pkl` files will be ignored
- Migration path: delete `.indexed/` and re-run indexing

### Migration Script (Optional)
```python
# packages/indexed-core/src/index/migrations/migrate_to_llama_index.py
def migrate_old_index(old_index_path):
    # Load old format
    old_index = load_old_faiss(old_index_path)
    old_mappings = load_old_mappings(old_index_path)
    
    # Convert to new format
    new_storage = StorageService(...)
    for vector, chunk_id, metadata in old_data:
        new_storage.add_vectors([vector], [chunk_id], [metadata])
    
    new_storage.save()
```

---

## 📚 Key Files to Modify

1. **`packages/indexed-core/src/index/services/storage.py`** (main changes)
2. **`packages/indexed-core/src/index/services/llama_query.py`** (new service)
3. **`packages/indexed-core/src/index/services/search.py`** (integrate llama_query)
4. **`packages/indexed-core/src/index/services/indexing.py`** (ensure content in metadata)

---

## 🔗 References

- [LlamaIndex FAISS Demo](https://developers.llamaindex.ai/python/examples/vector_stores/faissindexdemo/)
- [LlamaIndex FaissVectorStore Docs](https://docs.llamaindex.ai/en/stable/api_reference/storage/vector_store/faiss/)
- [Sentence Transformers trust_remote_code](https://www.sbert.net/docs/package_reference/SentenceTransformer.html)

---

## ✅ Success Criteria

- [ ] Old FAISS index can be deleted and rebuilt
- [ ] New index uses LlamaIndex `FaissVectorStore` format
- [ ] Search works with LlamaIndex query interface
- [ ] Cloud embeddings work for fast CLI queries (with HF token)
- [ ] Local embeddings fallback works (without HF token)
- [ ] MCP server loads model once and serves instant queries
- [ ] All existing tests pass (or are updated)
- [ ] V2 CLI commands work: `indexed-cli index files`, `indexed-cli index search`

---

## 💡 Future Enhancements (Post-Refactor)

1. **RAG Support:** Add LLM synthesis for generated answers
2. **Hybrid Search:** Combine dense + sparse (BM25) retrieval
3. **Re-ranking:** Use cross-encoder for better results
4. **Query Rewriting:** LLM-based query expansion
5. **Streaming:** Stream search results for large queries

---

**End of Brief**
