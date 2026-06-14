# Core Engine Architecture Guide

This package contains the heart of Indexed: document indexing, vector search, and collection management.

## V2 Core (LlamaIndex-Powered)

The v2 core engine lives at `src/core/v2/` alongside v1. It replaces the custom FAISS + sentence-transformers engine with **LlamaIndex**, **HuggingFace ONNX embeddings**, and **pluggable vector stores**.

### V2 Architecture

```
src/core/v2/
├── __init__.py              # Public API: Index, IndexConfig (NO side effects)
├── config.py                # Pydantic configs + register_config()
├── errors.py                # CoreV2Error hierarchy
├── embedding.py             # Lazy HuggingFace ONNX embeddings
├── vector_store.py          # Pluggable vector store factory (FAISS default)
├── storage.py               # Collection persistence via LlamaIndex StorageContext
├── adapter.py               # v1 connector output → LlamaIndex TextNode
├── ingestion.py             # Collection creation pipeline
├── retrieval.py             # Search/retrieval pipeline
├── index.py                 # Index facade
└── services/                # Service layer (same API contract as v1)
    ├── models.py            # Re-exports v1 service models
    ├── collection_service.py
    ├── search_service.py
    └── inspect_service.py
```

### V2 Key Patterns

- **No import-time side effects**: Config registration via explicit `register_config()`
- **Lazy loading**: All LlamaIndex/HuggingFace imports deferred to function bodies
- **Pre-chunked nodes**: Connectors already chunk; v2 bypasses LlamaIndex's node parsers
- **Pluggable vector stores**: FAISS default, extensible via `vector_store.py`
- **embed_model passed directly**: Avoids LlamaIndex's global `Settings` object

### V2 Usage

```python
from core.v2 import Index, IndexConfig
from core.v2.config import register_config

# Explicit config registration (call from app startup)
register_config(config_service)

# Use the Index facade
index = Index()
index.add_collection("docs", connector=files_connector)
results = index.search("authentication methods")
```

---

## V1 Core (Legacy)

## Package Overview

**Location:** `packages/indexed-core/`

**Purpose:**
- Orchestrate document indexing pipeline (read → convert → embed → persist)
- Perform semantic search via FAISS vector similarity
- Manage collections and provide high-level APIs
- Implement core business logic independent of CLI/MCP layers

**Key Responsibilities:**
- Read documents from connectors
- Convert documents to searchable chunks
- Generate vector embeddings using sentence-transformers
- Create and manage FAISS vector indexes
- Persist collections to disk with atomic operations
- Provide unified search interface

**Key Files:**
```
src/core/v1/
├── index.py                        # High-level Index facade
├── connectors/
│   ├── base.py                     # BaseConnector protocol
│   ├── models.py                   # Connector data models
│   └── protocol.py                 # Connector interface
├── engine/
│   ├── core/
│   │   ├── documents_collection_creator.py    # Indexing orchestration
│   │   └── documents_collection_searcher.py   # Search orchestration
│   ├── factories/
│   │   ├── create_collection_factory.py       # Creation pipeline
│   │   ├── search_collection_factory.py       # Search setup
│   │   └── update_collection_factory.py       # Update pipeline
│   ├── indexes/
│   │   ├── indexer_factory.py                 # FAISS indexer creation
│   │   ├── indexer_registry.py                # Registry of indexers
│   │   └── embeddings/                        # Embedding models
│   ├── persisters/
│   │   └── disk_persister.py                  # Atomic disk storage
│   └── services/
│       ├── collection_service.py              # Create/update operations
│       ├── search_service.py                  # Search orchestration
│       ├── inspect_service.py                 # Status & metadata
│       ├── update_service.py                  # Collection updates
│       ├── clear_service.py                   # Clear collections
│       └── models.py                          # Data models
├── constants.py                    # DEFAULT_INDEXER, model names
└── config_models.py               # Pydantic configuration schemas
```

## Three-Layer Architecture

```
┌────────────────────────────────────────────────┐
│  Index Facade (index.py)                       │
│  High-level API for library users              │
│  - index.create_collection()                   │
│  - index.search()                              │
│  - index.update_collection()                   │
└────────────────────┬─────────────────────────┘
                     │
┌────────────────────▼─────────────────────────┐
│  Service Layer (services/)                    │
│  Stateless orchestration                      │
│  - CollectionService                          │
│  - SearchService                              │
│  - InspectService                             │
│  - UpdateService                              │
│  - ClearService                               │
└────────────────────┬─────────────────────────┘
                     │
┌────────────────────▼─────────────────────────┐
│  Engine Layer (engine/)                       │
│  Core algorithms and persistence              │
│  - DocumentCollectionCreator                  │
│  - DocumentCollectionSearcher                 │
│  - FaissIndexer                               │
│  - SentenceEmbedder                           │
│  - DiskPersister                              │
└────────────────────┬─────────────────────────┘
                     │
┌────────────────────▼─────────────────────────┐
│  Infrastructure (connectors, config)          │
│  - Connectors (Jira, Confluence, Files)       │
│  - ConfigService                              │
│  - Utilities                                  │
└────────────────────────────────────────────────┘
```

## Index Facade Pattern

The `Index` class provides a simplified API for library users:

```python
from core.v1 import Index

index = Index()

# Create a collection
index.create_collection(
    name="my-docs",
    source_type="files",
    source_config={"path": "./documents"},
)

# Search collections
results = index.search(
    query="how to deploy",
    collection_name="my-docs",
    max_results=10,
)

# Get collection status
status = index.get_status("my-docs")
print(f"Documents: {status.document_count}")

# Update a collection
index.update_collection("my-docs")

# List collections
collections = index.list_collections()

# Delete a collection
index.remove_collection("my-docs")

# Clear all data from a collection
index.clear_collection("my-docs")
```

**Advantage:** Same API for both CLI commands and library usage without code duplication.

## Indexing Pipeline

Complete flow from documents to searchable collection:

### Step 1: Configuration Loading

```
CLI Input / Config File
    ↓
ConfigService.load()
    ├─ Read TOML config
    ├─ Merge environment variables
    ├─ Merge CLI overrides
    └─ Validate with Pydantic
    ↓
SourceConfig object (typed, validated)
```

### Step 2: Connector Initialization

```
SourceConfig
    ↓
Connector.from_config(config)
    ├─ Select connector type (Jira, Confluence, Files)
    ├─ Create DocumentReader
    ├─ Create DocumentConverter
    └─ Return initialized Connector
    ↓
Ready to fetch documents
```

### Step 3: Document Reading

```
Connector.reader.read_all_documents()
    ├─ Fetch documents from source (Jira issues, Confluence pages, files)
    ├─ Apply filtering if configured (JQL, CQL, file patterns)
    ├─ Return iterator of RawDocument objects
    └─ Memory efficient (stream, don't load all at once)
    ↓
Stream of RawDocument objects
```

### Step 4: Document Conversion

```
For each RawDocument:
    Connector.converter.convert(raw_doc)
    ├─ Parse document content
    ├─ Extract text and metadata
    ├─ Split into chunks (overlap configurable)
    ├─ Preserve source information (URL, issue key, file path)
    └─ Return DocumentChunk objects
    ↓
Stream of DocumentChunk objects with metadata
```

### Step 5: Embedding Generation

```
For batch of DocumentChunks:
    SentenceEmbedder.embed_texts(texts)
    ├─ Load embedding model (lazy, cached)
    ├─ Convert texts to embeddings (384 or 768 dims depending on model)
    ├─ Process in batches of 32 for efficiency
    └─ Return embedding vectors
    ↓
DocumentChunk objects with embedding vectors
```

### Step 6: FAISS Indexing

```
Embeddings + Metadata
    ↓
FaissIndexer.index_texts()
    ├─ Create FAISS index (IndexFlatL2 by default)
    ├─ Add embedding vectors to index
    ├─ Store chunk-to-document mapping
    └─ Generate index metadata
    ↓
Indexed collection ready for search
```

### Step 7: Persistence

```
Indexed data
    ↓
DiskPersister.persist()
    ├─ Create collection directory: ~/.indexed/data/collections/{name}/
    ├─ Save manifest.json (metadata)
    ├─ Save documents.json (document info)
    ├─ Save chunks.json (chunk text and metadata)
    ├─ Save index/ directory
    │   ├── index_info.json
    │   ├── index_document_mapping.json
    │   └── indexer_FAISS_*/indexer (binary FAISS index)
    ├─ Use atomic operations (temp files, rename)
    └─ Return collection manifest
    ↓
Collection persistent and ready for search
```

## Search Pipeline

Complete flow from query to results:

### Step 1: Query Reception

```
User Query
    ↓
SearchService.search(query, collection_name, max_results)
    ├─ Validate query
    ├─ Resolve collection(s) to search
    └─ Determine indexer to use
    ↓
Ready to search
```

### Step 2: Searcher Initialization/Retrieval

```
For each collection:
    SearchService._get_or_create_searcher(collection_name)
    ├─ Check searcher cache
    ├─ If cached: reuse searcher instance
    ├─ If not cached:
    │   ├─ Load collection manifest from disk
    │   ├─ Load collection metadata (documents, chunks)
    │   ├─ Load FAISS index (memory-mapped for efficiency)
    │   ├─ Create DocumentCollectionSearcher
    │   └─ Cache searcher instance
    └─ Return searcher
    ↓
Searcher ready for queries (may be cached from previous searches)
```

### Step 3: Query Embedding

```
Query Text
    ↓
SentenceEmbedder.embed_query(query)
    ├─ Use same embedding model as indexing
    ├─ Generate single embedding vector
    └─ Return embedding (384 or 768 dims)
    ↓
Query embedding vector
```

### Step 4: FAISS Search

```
Query Embedding
    ↓
FaissIndexer.search(query_embedding, top_k)
    ├─ Perform L2 distance similarity search
    ├─ Return indices of K nearest neighbors
    ├─ Convert L2 distances to similarity scores
    └─ Return (scores, indices)
    ↓
Top K results by similarity
```

### Step 5: Result Mapping

```
Indices + Scores
    ↓
DocumentCollectionSearcher.map_results()
    ├─ Look up chunk text by index
    ├─ Look up document metadata by chunk
    ├─ Construct SearchResult objects with:
    │   ├─ document text
    │   ├─ similarity score (0-1)
    │   ├─ source information (URL, issue key, etc.)
    │   └─ metadata
    └─ Return SearchResult list
    ↓
Search results with full context and metadata
```

### Step 6: Result Ranking & Filtering

```
SearchResult list
    ↓
Apply filters/ranking:
    ├─ Sort by score (highest first)
    ├─ Apply max_results limit
    ├─ Filter by collection if specified
    └─ Format for output (JSON, table, etc.)
    ↓
Final results ready for display
```

## Storage Architecture

### Collection Directory Structure

```
~/.indexed/data/collections/{collection-name}/
├── manifest.json              # Collection metadata
│   ├── name
│   ├── created_at
│   ├── updated_at
│   ├── source_type
│   ├── source_config (anonymized)
│   ├── document_count
│   ├── chunk_count
│   ├── indexer_type
│   └── embedding_model
│
├── documents.json             # Document-level metadata
│   ├── [
│   │   {
│   │     "id": "doc-001",
│   │     "source": "https://example.com/page1",
│   │     "title": "Page Title",
│   │     "chunk_count": 5,
│   │     "metadata": {...}
│   │   },
│   │   ...
│   │ ]
│
├── chunks.json                # Document chunks (the searchable content)
│   ├── [
│   │   {
│   │     "id": "chunk-001",
│   │     "document_id": "doc-001",
│   │     "text": "chunk text content",
│   │     "sequence": 0,
│   │     "metadata": {...}
│   │   },
│   │   ...
│   │ ]
│
└── index/                     # FAISS index files
    ├── index_info.json        # Index configuration
    │   ├── index_type: "IndexFlatL2"
    │   ├── embedding_dim: 384
    │   ├── chunk_count: 1000
    │   └── created_at
    │
    ├── index_document_mapping.json  # Maps FAISS result indices to chunks
    │   ├── [chunk_id, chunk_id, ...]
    │
    └── indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2/
        └── indexer            # Binary FAISS index file
```

### Storage Modes

**Global Mode (default):**
```
~/.indexed/
├── config.toml                # User configuration
├── .env                       # Credentials
└── data/
    └── collections/           # All collections
```

**Local Mode (per-project):**
```
./.indexed/
├── config.toml                # Project configuration
├── .env                       # Project credentials
└── data/
    └── collections/           # Project collections
```

## Service Layer APIs

### CollectionService

Stateless operations for collection management:

```python
from core.v1.engine.services import CollectionService

# Create collection
collection = CollectionService.create(
    name="my-docs",
    source_config=source_config,
)

# Update collection (re-index)
updated = CollectionService.update(
    collection_name="my-docs",
    source_config=new_source_config,  # optional
)

# Clear collection data
CollectionService.clear("my-docs")

# Get collection manifest
manifest = CollectionService.get_manifest("my-docs")
```

### SearchService

Orchestrates search across collections:

```python
from core.v1.engine.services import SearchService

# Search single collection
results = SearchService.search(
    query="deployment guide",
    collection_name="my-docs",
    max_results=10,
)

# Search all collections
results = SearchService.search(
    query="deployment guide",
    max_results=10,
)

# Results are SearchResult objects:
for result in results:
    print(f"Text: {result.text}")
    print(f"Score: {result.score}")
    print(f"Source: {result.source}")
    print(f"Metadata: {result.metadata}")
```

### InspectService

Collection status and metadata:

```python
from core.v1.engine.services import InspectService

# Get collection status
status = InspectService.get_status("my-docs")
print(f"Documents: {status.document_count}")
print(f"Chunks: {status.chunk_count}")
print(f"Embedding model: {status.embedding_model}")
print(f"Created: {status.created_at}")
print(f"Updated: {status.updated_at}")

# List all collections
collections = InspectService.list_collections()
for collection in collections:
    print(f"{collection.name}: {collection.document_count} docs")
```

### UpdateService

Collection updates and modifications:

```python
from core.v1.engine.services import UpdateService

# Update collection (re-index with new source config)
UpdateService.update_collection("my-docs", new_source_config)

# Get update history
history = UpdateService.get_update_history("my-docs")
for update in history:
    print(f"Updated at {update.timestamp}: {update.status}")
```

### ClearService

Data cleanup operations:

```python
from core.v1.engine.services import ClearService

# Clear all documents from collection (but keep metadata)
ClearService.clear_collection("my-docs")

# Clear specific collection entirely
ClearService.delete_collection("my-docs")
```

## Embedding Models

Supported embedding models (via sentence-transformers):

| Model | Dimensions | Size | Speed | Quality |
|-------|-----------|------|-------|---------|
| `all-MiniLM-L6-v2` | 384 | ~22MB | ✓ Fast | Good |
| `all-mpnet-base-v2` | 768 | ~420MB | Slower | Excellent |
| `multi-qa-distilbert-cos-v1` | 768 | ~260MB | Slower | Very Good |

**Default:** `all-MiniLM-L6-v2` (best balance of speed and quality)

**Configured via:**
```toml
[core.v1.embedding]
model_name = "all-MiniLM-L6-v2"
```

## FAISS Index Types

Supported FAISS indexes:

| Index Type | Speed | Memory | Best For |
|-----------|-------|--------|----------|
| `IndexFlatL2` | Very Fast | High | <50K documents (default) |
| `IndexIVFFlat` | Fast | Low | 50K-1M documents |
| `IndexHNSW` | Very Fast | Medium | 1M+ documents |

**Default:** `IndexFlatL2` (exact similarity search, best for typical use cases)

**Configured via:**
```toml
[core.v1.vector_store]
index_type = "IndexFlatL2"
```

## Factory Pattern

Complex object creation is delegated to factories:

### CreateCollectionFactory

Orchestrates the complete indexing pipeline:

```python
from core.v1.engine.factories import CreateCollectionFactory

factory = CreateCollectionFactory()

# Build and execute the entire indexing pipeline
collection = factory.create_collection(
    name="my-docs",
    source_config=source_config,
    progress_callback=lambda step, total: print(f"{step}/{total}"),
)
```

### SearchCollectionFactory

Sets up search infrastructure:

```python
from core.v1.engine.factories import SearchCollectionFactory

factory = SearchCollectionFactory()

# Create searcher with caching
searcher = factory.create_searcher("my-docs")

# Reuse for multiple queries
results1 = searcher.search("query1")
results2 = searcher.search("query2")  # Uses cached searcher
```

### UpdateCollectionFactory

Manages collection re-indexing:

```python
from core.v1.engine.factories import UpdateCollectionFactory

factory = UpdateCollectionFactory()

# Re-index with new source config
updated = factory.update_collection(
    name="my-docs",
    source_config=new_source_config,
)
```

## Key Components

### DocumentCollectionCreator

Orchestrates the complete indexing pipeline:

```python
from core.v1.engine.core import DocumentCollectionCreator

creator = DocumentCollectionCreator()

collection = creator.run(
    collection_name="my-docs",
    connector=connector,
    indexer=indexer,
    persister=persister,
    progress_callback=progress,
)
```

**Responsibilities:**
- Fetch documents from connector
- Convert to chunks
- Generate embeddings
- Create FAISS index
- Persist to disk

### DocumentCollectionSearcher

Handles search operations:

```python
from core.v1.engine.core import DocumentCollectionSearcher

searcher = DocumentCollectionSearcher(
    collection_name="my-docs",
    index=faiss_index,
    chunks=chunk_list,
    documents=document_list,
)

results = searcher.search(
    query_embedding=query_vector,
    top_k=10,
)
```

**Responsibilities:**
- Load FAISS index
- Map result indices to chunks
- Construct SearchResult objects
- Apply scoring and filtering

### FaissIndexer

Wraps FAISS functionality:

```python
from core.v1.engine.indexes import FaissIndexer

indexer = FaissIndexer(
    model_name="all-MiniLM-L6-v2",
    index_type="IndexFlatL2",
)

# Create index from embeddings
embeddings = [...]  # List of embedding vectors
faiss_index = indexer.index_texts(embeddings)

# Search
query_embedding = [...]  # Single query embedding
scores, indices = indexer.search(query_embedding, top_k=10)
```

### SentenceEmbedder

Generates embeddings using sentence-transformers:

```python
from core.v1.engine.indexes.embeddings import SentenceEmbedder

embedder = SentenceEmbedder(model_name="all-MiniLM-L6-v2")

# Single embedding
single = embedder.embed_query("search query")

# Batch embeddings (more efficient)
batch = embedder.embed_texts(["text1", "text2", "text3"])
```

**Lazy Loading:** Model is loaded on first use, then cached.

### DiskPersister

Atomic disk storage operations:

```python
from core.v1.engine.persisters import DiskPersister

persister = DiskPersister()

# Save collection
manifest = persister.persist(
    collection_name="my-docs",
    documents=document_list,
    chunks=chunk_list,
    index=faiss_index,
    metadata=collection_metadata,
)

# Load collection
collection_data = persister.load("my-docs")
```

**Atomic Operations:** Uses temp files and atomic rename to ensure consistency.

## Data Models

### Configuration Models (Pydantic)

```python
from core.v1.config_models import (
    IndexingConfig,
    SearchConfig,
    VectorStoreConfig,
    EmbeddingConfig,
)

# Validated configuration
indexing_config = IndexingConfig(
    chunk_size=512,
    chunk_overlap=50,
    batch_size=32,
)

search_config = SearchConfig(
    max_results=20,
    min_score=0.0,
)
```

### Service Models

```python
from core.v1.engine.services.models import (
    SearchResult,
    CollectionStatus,
    CollectionManifest,
)

# Search result
result = SearchResult(
    text="chunk text",
    score=0.95,
    source="https://example.com",
    document_id="doc-123",
    chunk_id="chunk-456",
    metadata={"title": "Page Title"},
)

# Collection status
status = CollectionStatus(
    name="my-docs",
    document_count=100,
    chunk_count=500,
    embedding_model="all-MiniLM-L6-v2",
    created_at=datetime.now(),
    updated_at=datetime.now(),
)
```

## Testing

### Testing Strategy

1. **Unit Tests:** Test individual components in isolation
2. **Integration Tests:** Test service layer with mocked engine
3. **System Tests:** Test complete pipelines with real data

### Example: Testing Search

```python
def test_search_service():
    """Test search across collections."""
    # Setup
    search_service = SearchService()
    mock_searcher = MagicMock()
    mock_searcher.search.return_value = [
        SearchResult(text="result1", score=0.95),
        SearchResult(text="result2", score=0.87),
    ]

    # Execute
    results = search_service.search(
        query="test query",
        max_results=10,
    )

    # Assert
    assert len(results) == 2
    assert results[0].score > results[1].score
```

### Running Tests

```bash
# All core tests
uv run pytest tests/unit/indexed_core/ -q

# Specific test file
uv run pytest tests/unit/indexed_core/test_search_service.py -v

# With coverage
uv run pytest tests/unit/indexed_core/ -q --cov=core
```

## Performance Characteristics

### Indexing Performance

- **Throughput:** 100+ documents per minute
- **Embedding generation:** ~30-50ms per 32 documents
- **FAISS indexing:** <100ms for 10K documents
- **Disk write:** ~500ms for 10K documents

### Search Performance

- **Query latency:** <1s for typical queries on 10K-100K documents
- **Embedding generation:** <50ms per query
- **FAISS search:** <500ms for similarity search
- **Result formatting:** <100ms

### Memory Usage

- **Embedding model:** ~200MB resident
- **FAISS index:** ~4 bytes per embedding per dimension (1.5MB for 100K documents with 384-dim model)
- **Searcher cache:** ~300MB for 5 active collections

## Related Documentation

- **[Root CURSOR.md](../../CURSOR.md)** - Project overview
- **[CLI CURSOR.md](../../apps/indexed/CURSOR.md)** - CLI commands
- **[Connectors CURSOR.md](../../packages/indexed-connectors/CURSOR.md)** - Connector system
- **[Configuration CURSOR.md](../../packages/indexed-config/CURSOR.md)** - Config system
- **[.cursor/rules/tech/architecture.mdc](../../.cursor/rules/tech/architecture.mdc)** - Full architecture

---

**Last Updated:** January 24, 2026
