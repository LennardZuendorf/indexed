# System Architecture

## Overview

Indexed is a document search system built with a privacy-first monorepo structure. The current focus is establishing a clean foundation with working CLI functionality, then enhancing with Rich UI components, and eventually building a web server UI.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer (indexed-cli)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   create     │  │   search     │  │   inspect    │          │
│  │   command    │  │   command    │  │   command    │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
└─────────┼──────────────────┼──────────────────┼─────────────────┘
          │                  │                  │
          │    ┌─────────────▼──────────────┐   │
          │    │   ConfigService            │   │
          │    │   - Load/Save TOML         │   │
          │    │   - Validate with Pydantic │   │
          └────┤   - Merge configs          ├───┘
               └─────────────┬──────────────┘
                             │
                    ┌────────▼─────────┐
                    │  ServiceFactory  │
                    │  (Dependency     │
                    │   Injection)     │
                    └────────┬─────────┘
                             │
          ┌──────────────────┴──────────────────┐
          │                                     │
┌─────────▼──────────┐              ┌──────────▼──────────┐
│  IndexController   │              │  SearchController   │
│  ┌──────────────┐  │              │  ┌──────────────┐   │
│  │create_index  │  │              │  │search        │   │
│  │update_index  │  │              │  │search_filters│   │
│  │rebuild_index │  │              │  │              │   │
│  └──────────────┘  │              │  └──────────────┘   │
└─────────┬──────────┘              └──────────┬──────────┘
          │                                     │
┌─────────▼──────────────────────────┐         │
│      IndexingService                │         │
│  ┌──────────────────────────────┐  │         │
│  │ 1. Discover documents        │  │         │
│  │ 2. Read documents            │  │         │
│  │ 3. Chunk documents           │  │         │
│  │ 4. Generate embeddings       │  │         │
│  │ 5. Store vectors             │  │         │
│  └──────────────────────────────┘  │         │
└─────────┬──────────┬────────────────┘         │
          │          │                          │
          │          │         ┌────────────────▼──────────┐
          │          │         │     SearchService          │
          │          │         │  ┌──────────────────────┐  │
          │          │         │  │ 1. Embed query       │  │
          │          │         │  │ 2. Search vectors    │  │
          │          │         │  │ 3. Retrieve chunks   │  │
          │          │         │  │ 4. Format results    │  │
          │          │         │  └──────────────────────┘  │
          │          │         └────────────┬────────────────┘
          │          │                      │
          │          │         ┌────────────▼────────────┐
          │          └─────────►  EmbeddingService       │
          │                    │  ┌───────────────────┐  │
          │                    │  │sentence-          │  │
          │                    │  │transformers       │  │
          │                    │  │OpenAI             │  │
          │                    │  │Voyage AI          │  │
          │                    │  │                   │  │
          │                    │  │embed_text()       │  │
          │                    │  │embed_batch()      │  │
          │                    │  └───────────────────┘  │
          │                    └─────────────────────────┘
          │
┌─────────▼─────────────────────┐
│     StorageService             │
│  ┌──────────────────────────┐  │
│  │ FAISS Vector Store       │  │
│  │                          │  │
│  │ add_vectors()            │  │
│  │ search()                 │  │
│  │ delete_by_ids()          │  │
│  │ save() / load()          │  │
│  └──────────────────────────┘  │
└────────────────────────────────┘
          ▲
          │
┌─────────┴──────────────────────┐
│  DocumentConnectors            │
│  ┌──────────────────────────┐  │
│  │ FileSystemConnector      │  │
│  │ - discover_documents()   │  │
│  │ - read_document()        │  │
│  │                          │  │
│  │ JiraConnector (legacy)   │  │
│  │ ConfluenceConnector      │  │
│  └──────────────────────────┘  │
└────────────────────────────────┘
```

## Component Architecture

### 1. CLI Layer (`apps/indexed-cli`)

**Responsibility:** User interface and command routing

**Structure:**
```
indexed-cli/
├── app.py              # Main Typer application
├── commands/           # Command implementations
│   ├── create.py      # Create collections
│   ├── search.py      # Search commands
│   ├── delete.py      # Delete collections
│   └── legacy.py      # Legacy command wrappers
├── engines/           # Engine selection (legacy vs new)
└── server/
    └── mcp.py         # MCP server implementation
```

**Key Responsibilities:**
- Parse command-line arguments
- Load configuration
- Initialize service factory
- Display results to user
- Handle user errors gracefully

### 2. Controller Layer (`packages/indexed-core/src/index/controllers`)

**Responsibility:** Orchestration and coordination between services

**Controllers:**
- `IndexController` - Manages indexing operations
- `SearchController` - Manages search operations

**Pattern:**
```python
class IndexController:
    def __init__(
        self,
        indexing_service: IndexingService,
        config: IndexConfig
    ):
        self.indexing_service = indexing_service
        self.config = config
    
    def create_index(self, sources: List[str]) -> IndexStats:
        # Orchestrate indexing workflow
        # Coordinate multiple services
        # Return results
```

### 3. Service Layer (`packages/indexed-core/src/index/services`)

**Responsibility:** Business logic and core functionality

**Services:**

**IndexingService:**
- Document discovery and reading
- Chunking and processing
- Embedding generation coordination
- Vector storage coordination

**SearchService:**
- Query processing
- Vector similarity search
- Result retrieval and formatting

**EmbeddingService:**
- Text embedding generation
- Multiple provider support (sentence-transformers, OpenAI, Voyage AI)
- Batch processing optimization

**StorageService:**
- FAISS vector store management
- Vector addition and deletion
- Similarity search
- Persistence to disk

### 4. Infrastructure Layer

**Components:**

**Connectors (`packages/indexed-core/src/index/connectors`):**
- `FileSystemConnector` - Local file reading
- `JiraConnector` (legacy) - Jira integration
- `ConfluenceConnector` (legacy) - Confluence integration

**Configuration (`packages/indexed-core/src/index/config`):**
- `ConfigService` - Load/save TOML configuration
- Pydantic models for validation
- Environment variable overrides

**Storage:**
- FAISS index files
- Document metadata
- Collection manifests

## Data Flow: Indexing Pipeline

```
User Command: indexed-cli create files -c my-docs --basePath /path
│
├─► 1. CLI loads config via ConfigService
│       └─► Reads config.toml, validates with Pydantic
│
├─► 2. CLI calls ServiceFactory.create_from_config()
│       ├─► Instantiates EmbeddingService (based on config)
│       ├─► Instantiates StorageService (FAISS)
│       ├─► Instantiates FileSystemConnector
│       ├─► Instantiates IndexingService
│       └─► Instantiates IndexController
│
├─► 3. CLI calls IndexController.create_index(["/path"])
│       │
│       └─► IndexController.create_index()
│               │
│               └─► IndexingService.index_source("/path")
│                       │
│                       ├─► FileSystemConnector.discover_documents()
│                       │       └─► Returns: Iterator[Path] of matching files
│                       │
│                       ├─► FileSystemConnector.read_document(path)
│                       │       └─► Returns: Document object
│                       │
│                       ├─► IndexingService._chunk_document(document)
│                       │       └─► Returns: List[Chunk]
│                       │
│                       ├─► EmbeddingService.embed_batch([chunk.content, ...])
│                       │       └─► Returns: numpy.ndarray (embeddings)
│                       │
│                       └─► StorageService.add_vectors(embeddings, chunk_ids)
│                               └─► Stores in FAISS index
│
└─► 4. IndexController returns stats
        └─► CLI displays: "Indexed N chunks from M documents"
```

## Data Flow: Search Pipeline

```
User Command: indexed-cli search "authentication flow"
│
├─► 1. CLI loads config and creates services (via factory)
│
├─► 2. CLI calls SearchController.search("authentication flow")
│       │
│       └─► SearchController.search()
│               │
│               └─► SearchService.search("authentication flow", top_k=10)
│                       │
│                       ├─► EmbeddingService.embed_text("authentication flow")
│                       │       └─► Returns: numpy.ndarray (query embedding)
│                       │
│                       ├─► StorageService.search(query_embedding, top_k=10)
│                       │       └─► Returns: [(chunk_id, score), ...]
│                       │
│                       ├─► SearchService retrieves Chunk objects by IDs
│                       │       └─► From metadata store
│                       │
│                       └─► SearchService creates SearchResult objects
│                               └─► Returns: List[SearchResult]
│
└─► 3. CLI formats and displays results
```

## Configuration Hierarchy

```
Configuration Sources (lowest to highest priority):
1. Default values (hardcoded in Pydantic models)
2. Global config (~/.config/indexed/config.toml)
3. Workspace config (./config.toml)
4. Environment variables (INDEXED__*)
5. Command-line arguments

Example:
┌─────────────────────────────────────┐
│ Command-line: --chunk-size 1024     │ (Highest priority)
└──────────────┬──────────────────────┘
               │ overrides
┌──────────────▼──────────────────────┐
│ ENV: INDEXED__CHUNK_SIZE=512        │
└──────────────┬──────────────────────┘
               │ overrides
┌──────────────▼──────────────────────┐
│ Workspace config.toml:              │
│ [indexing]                          │
│ chunk_size = 256                    │
└──────────────┬──────────────────────┘
               │ overrides
┌──────────────▼──────────────────────┐
│ Global config:                      │
│ [indexing]                          │
│ chunk_size = 128                    │
└──────────────┬──────────────────────┘
               │ overrides
┌──────────────▼──────────────────────┐
│ Default: chunk_size = 512           │ (Lowest priority)
└─────────────────────────────────────┘
```

## Dependency Injection Pattern

**ServiceFactory** is the composition root:

```python
class ServiceFactory:
    @staticmethod
    def create_from_config(config: IndexConfig):
        # 1. Create infrastructure components
        embedding_service = create_embedding_service(config.embedding)
        storage_service = create_storage_service(config.vector_store)
        connectors = create_connectors(config.connectors)
        
        # 2. Create services with injected dependencies
        indexing_service = IndexingService(
            embedding_service=embedding_service,
            storage_service=storage_service,
            connectors=connectors,
            config=config.indexing
        )
        
        search_service = SearchService(
            embedding_service=embedding_service,
            storage_service=storage_service,
            config=config.search
        )
        
        # 3. Create controllers with injected services
        index_controller = IndexController(
            indexing_service=indexing_service,
            config=config
        )
        
        search_controller = SearchController(
            search_service=search_service,
            config=config
        )
        
        return index_controller, search_controller, config
```

**Key Principles:**
1. No service instantiates its own dependencies
2. All dependencies passed via constructor
3. Easy to test with mocks
4. Clear dependency graph

## Extension Points

### 1. Adding a New Embedding Provider

```python
# Implement EmbeddingProvider protocol
class AnthropicEmbeddingProvider:
    def embed_text(self, text: str) -> np.ndarray:
        # Call Anthropic API
        pass
    
    def embed_batch(self, texts: List[str]) -> np.ndarray:
        # Batch embedding
        pass

# Register in factory
def create_embedding_service(config: EmbeddingConfig):
    if config.provider == "sentence-transformers":
        return SentenceTransformerEmbedding(...)
    elif config.provider == "openai":
        return OpenAIEmbedding(...)
    elif config.provider == "anthropic":
        return AnthropicEmbeddingProvider(...)
```

### 2. Adding a New Connector

```python
# Implement DocumentConnector protocol
class GitConnector:
    def discover_documents(self, source: str) -> Iterator[Path]:
        # Clone repo, list files
        pass
        
    def read_document(self, path: Path) -> Document:
        # Read file content
        pass

# Register in factory
if config.connectors.git_enabled:
    connectors.append(GitConnector(...))
```

### 3. Swapping Vector Store

```python
# Add new storage service implementation
class QdrantStorageService:
    def add_vectors(self, vectors: np.ndarray, ids: List[str]) -> None:
        # Upload to Qdrant
        pass
    
    def search(self, query_vector: np.ndarray, top_k: int) -> List[Tuple[str, float]]:
        # Query Qdrant
        pass

# Update factory
if config.vector_store.type == "faiss":
    storage_service = StorageService(...)
elif config.vector_store.type == "qdrant":
    storage_service = QdrantStorageService(...)
```

## Storage Architecture

### Directory Structure

```
./data/                          # Data root
├── collections/                 # Collection storage
│   └── {collection_name}/
│       ├── documents/           # Document metadata
│       │   └── *.json
│       └── indexes/             # Vector indexes
│           ├── index_info.json
│           ├── index_document_mapping.json
│           ├── reverse_index_document_mapping.json
│           └── indexer_FAISS_*/
│               └── indexer      # FAISS index file
└── caches/                      # Temporary caches
    └── {hash}/
        └── *.json
```

### File Formats

**Document Metadata (`documents/*.json`):**
```json
{
  "id": "doc-123",
  "source_path": "/path/to/file.md",
  "content": "...",
  "metadata": {
    "filename": "file.md",
    "size": 1024,
    "modified": "2024-01-01T00:00:00"
  }
}
```

**Index Info (`indexes/index_info.json`):**
```json
{
  "indexer_type": "FAISS_IndexFlatL2",
  "embedding_model": "all-MiniLM-L6-v2",
  "dimension": 384,
  "document_count": 100,
  "chunk_count": 500
}
```

## Legacy vs New Architecture

### Current State

**Legacy Implementation** (`packages/indexed-core/src/index/legacy/`):
- Factory pattern with adapters
- Complex abstraction layers
- Works but hard to test and extend

**New Implementation** (`packages/indexed-core/src/index/`):
- Controller/Service pattern
- Dependency injection
- Clean, testable, extensible

### Migration Strategy

1. **Coexistence**: Both implementations exist
2. **Engine Selection**: CLI chooses which engine to use
3. **Gradual Migration**: Move features one at a time
4. **Data Compatibility**: Both use same storage format

```python
# Engine selection in CLI
if use_legacy:
    from indexed_cli.engines.legacy_engine import LegacyEngine
    engine = LegacyEngine()
else:
    from indexed_cli.engines.v2_engine import V2Engine
    engine = V2Engine()
```

## Key Design Principles

1. **Separation of Concerns**: Each component has single responsibility
2. **Dependency Inversion**: Depend on abstractions, not implementations
3. **Open/Closed Principle**: Open for extension, closed for modification
4. **Configuration over Code**: Behavior controlled by config files
5. **Testability**: All dependencies injected, easy to mock
6. **Type Safety**: Pydantic validation, type hints throughout

## Performance Considerations

### Optimization Strategies

1. **Batch Processing**: Embed multiple texts in one call
2. **Lazy Loading**: Load indexes only when needed
3. **Caching**: Cache embedding results and search queries
4. **Memory Mapping**: Use memory-mapped FAISS indexes
5. **Parallel Processing**: Process documents concurrently

### Scalability

**Current (Local):**
- Single machine
- Up to 100K documents
- FAISS IndexFlatL2

**Future (Server):**
- Distributed processing
- Cloud vector stores (Qdrant, pgvector)
- Horizontal scaling
- Load balancing

---

This architecture provides a solid foundation for building a maintainable, extensible document search system while enabling smooth evolution from local-first to cloud-ready deployment.

