# Indexed Architecture Overview

## System Architecture Diagram

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
│  │ GitConnector (future)    │  │
│  │ NotionConnector (future) │  │
│  └──────────────────────────┘  │
└────────────────────────────────┘
```

## Data Flow: Indexing Pipeline

```
User Command: `indexed create /path/to/docs`
│
├─► 1. CLI loads config via ConfigService
│       └─► Reads ~/.indexed/config.toml or workspace config
│
├─► 2. CLI calls ServiceFactory.create_from_config()
│       ├─► Instantiates EmbeddingService
│       ├─► Instantiates StorageService
│       ├─► Instantiates Connectors (FileSystem, etc.)
│       ├─► Instantiates IndexingService
│       └─► Instantiates IndexController
│
├─► 3. CLI calls IndexController.create_index(["/path/to/docs"])
│       │
│       └─► IndexController.create_index()
│               │
│               └─► IndexingService.index_source("/path/to/docs")
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
User Command: `indexed search "authentication flow"`
│
├─► 1. CLI loads config and creates services
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
│                       │       └─► From metadata store or recreate from storage
│                       │
│                       └─► SearchService creates SearchResult objects
│                               └─► Returns: List[SearchResult]
│
└─► 3. CLI formats and displays results
```

## Configuration Hierarchy

```
Global Config (~/.indexed/config.toml)
    │
    ├─► Default settings for all workspaces
    │   ├─► embedding.model_name = "all-MiniLM-L6-v2"
    │   ├─► vector_store.type = "faiss"
    │   └─► indexing.chunk_size = 512
    │
    └─► Can be overridden by workspace config
            │
            └─► Workspace Config (workspace/.indexed/config.toml)
                    │
                    ├─► workspace.root_path = "/path/to/workspace"
                    ├─► indexing.include_patterns = ["*.py", "*.rs"]
                    └─► Merged with global config (workspace takes precedence)
```

## Component Responsibilities

### Controllers (Orchestration Layer)
- **IndexController**: High-level indexing operations (create, update, rebuild)
- **SearchController**: High-level search operations
- Coordinate between multiple services
- Return formatted results to CLI
- Handle error cases and validation

### Services (Business Logic Layer)
- **IndexingService**: Document ingestion, chunking, embedding coordination
- **SearchService**: Query processing, result retrieval
- **EmbeddingService**: Text embedding generation
- **StorageService**: Vector storage and similarity search
- Single responsibility per service
- Stateless when possible

### Infrastructure Layer
- **Connectors**: Document discovery and reading
- **Storage**: FAISS vector store wrapper
- **Config**: Configuration loading and validation
- Pluggable implementations

## Dependency Injection Pattern

```python
# CLI is the composition root
config_service = ConfigService()
config = config_service.load_config()

# Factory creates all dependencies
index_controller, search_controller, config = ServiceFactory.create_from_config(config)

# Dependencies flow from top to bottom:
# IndexController → IndexingService → [EmbeddingService, StorageService, Connectors]
# SearchController → SearchService → [EmbeddingService, StorageService]

# No service instantiates its own dependencies
# All dependencies passed via constructor
```

## Extension Points

### 1. Adding a New Connector
```python
# Implement DocumentConnector protocol
class NotionConnector:
    def discover_documents(self, source: str) -> Iterator[Path]:
        # Connect to Notion API, list pages
        
    def read_document(self, path: Path) -> Document:
        # Fetch page content from Notion
        
    def supports_path(self, path: Path) -> bool:
        return path.startswith("notion://")

# Register in factory
if config.connectors.notion_enabled:
    connectors.append(NotionConnector(...))
```

### 2. Swapping Vector Store
```python
# Add new storage service implementation
class QdrantStorageService:
    def __init__(self, url: str, collection_name: str):
        self.client = QdrantClient(url)
        self.collection_name = collection_name
    
    def add_vectors(self, vectors: np.ndarray, ids: List[str]) -> None:
        # Upload to Qdrant
    
    def search(self, query_vector: np.ndarray, top_k: int) -> List[Tuple[str, float]]:
        # Query Qdrant

# Update factory to select based on config
if config.vector_store.type == "faiss":
    storage_service = StorageService(...)
elif config.vector_store.type == "qdrant":
    storage_service = QdrantStorageService(...)
```

### 3. Using Different Embedding Provider
```python
# Add new embedding service implementation
class OpenAIEmbeddingService:
    def __init__(self, api_key: str, model_name: str):
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name
    
    def embed_text(self, text: str) -> np.ndarray:
        response = self.client.embeddings.create(
            input=text,
            model=self.model_name
        )
        return np.array(response.data[0].embedding)

# Update factory
if config.embedding.provider == "sentence-transformers":
    embedding_service = EmbeddingService(...)
elif config.embedding.provider == "openai":
    embedding_service = OpenAIEmbeddingService(...)
```

## Key Design Principles

1. **Separation of Concerns**: Each component has a single, well-defined responsibility
2. **Dependency Inversion**: High-level modules don't depend on low-level modules; both depend on abstractions
3. **Open/Closed Principle**: Open for extension (new connectors, stores) but closed for modification
4. **Configuration over Code**: Behavior controlled by config files, not code changes
5. **Testability**: All dependencies injected, easy to mock for testing
6. **Type Safety**: Pydantic for config validation, type hints throughout

## Testing Architecture

```
Unit Tests (Fast, Isolated)
├─► Test ConfigService with mock TOML files
├─► Test EmbeddingService with mock model
├─► Test StorageService with in-memory FAISS
├─► Test IndexingService with mocked dependencies
└─► Test Controllers with mocked services

Integration Tests (Slower, End-to-End)
├─► Test full indexing pipeline with real files
├─► Test search pipeline with real embeddings
└─► Test config-driven service instantiation

Fixtures
├─► sample_documents/ - Test documents (markdown, code)
├─► test_configs/ - Various config combinations
└─► Mock objects for services
```

---

**This architecture provides:**
- ✅ Clean separation of concerns
- ✅ Easy testability through dependency injection
- ✅ Configuration-driven behavior
- ✅ Pluggable components (connectors, embedding models, vector stores)
- ✅ Clear upgrade path from legacy code
- ✅ Scalability to future features
