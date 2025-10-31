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
│  │ JiraConnector            │  │
│  │ - BaseConnector compliant│  │
│  │ ConfluenceConnector      │  │
│  │ - BaseConnector compliant│  │
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

**Connectors (`packages/indexed-connectors/src/connectors/`):**
- `FileSystemConnector` - Local file reading  
- `JiraConnector`, `JiraCloudConnector` - Jira integration (uses `atlassian-python-api`)
  - ✅ BaseConnector protocol compliant
  - ✅ Configuration-driven instantiation
  - ✅ Standardized environment variable handling
- `ConfluenceConnector`, `ConfluenceCloudConnector` - Confluence integration
  - ✅ BaseConnector protocol compliant  
  - ✅ Configuration-driven instantiation
  - ✅ Standardized environment variable handling
- `BitbucketConnector` (future) - Bitbucket integration

**BaseConnector Protocol Architecture:**

All Atlassian connectors implement the BaseConnector protocol for standardized configuration-driven instantiation:

```python
class BaseConnector(Protocol):
    @classmethod
    def config_spec(cls) -> ConnectorMetadata:
        """Return configuration specification."""
    
    @classmethod
    def from_config(cls, config_service, namespace: str) -> Self:
        """Create connector instance from configuration."""
```

**Environment Variable Resolution Order:**
1. Direct config attributes (highest priority)
2. Configured environment variable names  
3. Standard fallback environment variables

**Common Patterns:**
- `safe_getattr()` utility for test compatibility (handles MagicMock values)
- Consistent error messages for validation failures
- Standardized configuration validation patterns

**Atlassian Integration Strategy:**
- **Unified Dependency**: All Atlassian services use `atlassian-python-api>=4.0.7`
- **Consistent Patterns**: Same authentication and pagination patterns across services
- **Cloud + Server/DC**: Single library supports both deployment models
- **Future-Ready**: Prepared for Bitbucket connector implementations

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

## Configuration System

### Architecture

**Single Source of Truth**: `indexed-config` package provides unified configuration management.

```
Config Sources (Priority: Low → High)
├── Pydantic Model Defaults
├── Global Config (~/.config/indexed/config.toml)
├── Workspace Config (./.indexed/config.toml)
└── Environment Variables (INDEXED__*)

                ↓

        ConfigService
        ├── register(spec, path)
        ├── bind() → Provider
        ├── set(path, value)
        ├── delete(path)
        └── validate()

                ↓

          Provider
          ├── get(Type[T]) → T
          └── get_by_path(str) → BaseModel
```

### Core Principles

1. **Explicit Registration**: Components register their own config specs at usage point
2. **Zero Coupling**: Config doesn't know about consumers
3. **Type Safety**: Pydantic validation throughout
4. **Version Awareness**: Namespaced paths support multiple versions (`core.v1.*`, `core.v2.*`)

### Usage Pattern

```python
from indexed_config import ConfigService
from connectors.jira import JiraCloudConnector

# Initialize config
config = ConfigService()

# Override with CLI args if needed
config.set("sources.jira_cloud.url", "https://company.atlassian.net")

# Connector registers its own config spec and extracts values
connector = JiraCloudConnector.from_config(config)
```

### Config Hierarchy Example

```
┌─────────────────────────────────────┐
│ ENV: INDEXED__core__v1__indexing__  │
│      chunk_size=1024                │ (Highest priority)
└──────────────┬──────────────────────┘
               │ overrides
┌──────────────▼──────────────────────┐
│ Workspace .indexed/config.toml:     │
│ [core.v1.indexing]                  │
│ chunk_size = 512                    │
└──────────────┬──────────────────────┘
               │ overrides
┌──────────────▼──────────────────────┐
│ Global ~/.config/indexed/config.toml│
│ [core.v1.indexing]                  │
│ chunk_size = 256                    │
└──────────────┬──────────────────────┘
               │ overrides
┌──────────────▼──────────────────────┐
│ Default: chunk_size = 512           │ (Lowest priority)
└─────────────────────────────────────┘
```

### Configuration Paths

**Connectors** (`sources.*`):
- `sources.jira` - Jira Server/DC
- `sources.jira_cloud` - Jira Cloud
- `sources.confluence` - Confluence Server/DC
- `sources.confluence_cloud` - Confluence Cloud
- `sources.files` - File System

**Core v1** (`core.v1.*`):
- `core.v1.indexing` - Indexing pipeline config
- `core.v1.embedding` - Embedding generation config
- `core.v1.storage` - Vector storage config
- `core.v1.search` - Search behavior config

**Infrastructure**:
- `paths` - File system paths
- `mcp` - MCP server settings
- `performance` - Caching and performance
- `logging` - Logging configuration

See `.memory/config_api.md` for complete API documentation.

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

## Architecture Evolution (v1.0)

### Current State

**v1.0 Implementation** (`packages/indexed-core/src/core/v1/`):
- Clean Controller/Service pattern
- Protocol-based connector interface (BaseConnector)
- Dependency injection via ServiceFactory
- Unified configuration with Pydantic
- Dynamic connector registry for discovery/compatibility

**Legacy Code**: No legacy implementation remains in v1.0. All code uses `core.v1` architecture.

### Connector Registry Purpose

The dynamic connector registry (`indexed/src/indexed/connectors/`) serves infrastructure needs:
- **Discovery**: Automatically find all available connectors
- **Compatibility**: Version checking between connectors and core
- **Introspection**: List available connectors programmatically

**Not a full plugin system**: CLI remains hardcoded for UX quality (proper --help, type safety, validation).

**Optional future**: `indexed index create --from-registry` for advanced users (deferred).

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

