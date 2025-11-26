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
          ┌──────────────────┴──────────────────┐
          │                                     │
┌─────────▼──────────────────────────┐ ┌───────▼───────────────────┐
│   collection_service (functions)   │ │   SearchService (class)    │
│  ┌──────────────────────────────┐  │ │  ┌──────────────────────┐  │
│  │ create(configs, ...)        │  │ │  │ search(query, ...)   │  │
│  │ update(configs, ...)        │  │ │  │ (caches searchers)   │  │
│  │ clear(collection_names)     │  │ │  └──────────────────────┘  │
│  └──────────────────────────────┘  │ └────────────┬──────────────┘
└─────────┬──────────┬───────────────┘              │
          │          │                              │
          │          │    ┌─────────────────────────▼──────────┐
          │          │    │  InspectService (class)            │
          │          │    │  ┌──────────────────────────────┐  │
          │          │    │  │ status(collections)          │  │
          │          │    │  │ inspect(collections)         │  │
          │          │    │  └──────────────────────────────┘  │
          │          │    └────────────────────────────────────┘
          │          │
┌─────────▼──────────▼─────────────────┐
│    DocumentCollectionCreator         │
│  ┌──────────────────────────────┐    │
│  │ 1. Read documents (Reader)   │    │
│  │ 2. Convert (Converter)       │    │
│  │ 3. Index (FaissIndexer)      │    │
│  │ 4. Persist (DiskPersister)   │    │
│  └──────────────────────────────┘    │
└─────────┬────────────────────────────┘
          │
          │         ┌────────────────────────────┐
          └─────────►  FaissIndexer              │
                    │  ┌──────────────────────┐  │
                    │  │ SentenceEmbedder     │  │
                    │  │ FAISS IndexFlatL2    │  │
                    │  │ index_texts()        │  │
                    │  │ search()             │  │
                    │  └──────────────────────┘  │
                    └────────────────────────────┘
          ▲
          │
┌─────────┴──────────────────────┐
│  DocumentConnectors            │
│  ┌──────────────────────────┐  │
│  │ FileSystemConnector      │  │
│  │ JiraConnector            │  │
│  │ JiraCloudConnector       │  │
│  │ ConfluenceConnector      │  │
│  │ ConfluenceCloudConnector │  │
│  │ - All BaseConnector      │  │
│  │   protocol compliant     │  │
│  └──────────────────────────┘  │
└────────────────────────────────┘
```

## Architectural Pattern: Facade + Services

Indexed uses a **simplified Facade pattern** rather than a traditional Controller/Service layering:

1. **CLI Commands** call **Service Functions** directly
2. **Index Facade** (`core.v1.Index`) wraps services for library users
3. **Services** handle business logic
4. **Infrastructure** handles I/O and external systems

This keeps the architecture simple (KISS) while providing clean APIs for both CLI and library usage.

## Component Architecture

### 1. CLI Layer (`indexed/src/indexed/`)

**Responsibility:** User interface and command routing

**Structure:**
```
indexed/
├── app.py              # Main Typer application
├── knowledge/          # Knowledge/Index commands
│   └── commands/
│       ├── create.py   # Create collections (jira, confluence, files)
│       ├── search.py   # Search commands
│       ├── inspect.py  # Inspect collections
│       ├── update.py   # Update collections
│       └── remove.py   # Remove collections
├── config/             # Configuration commands
│   └── cli.py          # inspect, update, set, delete, validate
├── mcp/                # MCP server
│   └── server.py       # FastMCP integration
└── utils/              # CLI utilities
    ├── components/     # Rich UI components
    ├── progress_bar.py # Progress indicators
    └── console.py      # Console configuration
```

**Key Responsibilities:**
- Parse command-line arguments
- Load configuration via ConfigService
- Call service functions directly
- Display results with Rich UI
- Handle user errors gracefully

### 2. Service Layer (`packages/indexed-core/src/core/v1/engine/services/`)

**Responsibility:** Business logic and core functionality

**Services:**

**collection_service.py** (functional):
- `create(configs, ...)` - Create new collections
- `update(configs, ...)` - Update existing collections
- `clear(collection_names)` - Delete collections

**SearchService** (class-based, stateful):
- Caches searcher instances for performance
- `search(query, collections, ...)` - Execute semantic search

**InspectService** (class-based, stateful):
- Caches manifests for performance
- `status(collections)` - Get collection status
- `inspect(collections, ...)` - Get detailed collection info

### 3. Index Facade (`packages/indexed-core/src/core/v1/index.py`)

**Responsibility:** High-level API for library users

```python
from core.v1 import Index

# Library usage pattern
index = Index()
index.create("my-collection", connector)
results = index.search("query", collection="my-collection")
status = index.status()
```

The Index class wraps service layer functions, providing a clean OOP interface for programmatic usage.

### 4. Infrastructure Layer

**Components:**

**Connectors (`packages/indexed-connectors/src/connectors/`):**
- `FileSystemConnector` - Local file reading  
- `JiraConnector`, `JiraCloudConnector` - Jira integration
- `ConfluenceConnector`, `ConfluenceCloudConnector` - Confluence integration

All connectors implement the **BaseConnector protocol**:
```python
class BaseConnector(Protocol):
    @property
    def reader(self) -> DocumentReader: ...
    
    @property
    def converter(self) -> DocumentConverter: ...
    
    @property
    def connector_type(self) -> str: ...
    
    @classmethod
    def from_dto(cls, config: BaseModel) -> "BaseConnector": ...
```

**Configuration (`packages/indexed-config/`):**
- `ConfigService` - Load/save TOML configuration
- Pydantic models for validation
- Automatic .env handling for secrets

**Storage:**
- FAISS index files
- Document metadata JSON
- Collection manifests

## Data Flow: Indexing Pipeline

```
User Command: indexed index create jira --url https://company.atlassian.net
│
├─► 1. CLI initializes ConfigService (auto-loads .env)
│       └─► Loads: config.toml + .env files
│
├─► 2. CLI validates requirements using Pydantic model introspection
│       │
│       └─► config.validate_requirements(
│               config_class=JiraCloudConfig,
│               namespace="sources.jira_cloud",
│               cli_overrides={"url": "..."}
│           )
│           │
│           ├─► Introspects JiraCloudConfig fields
│           ├─► Checks CLI > config > env for each field
│           ├─► Identifies missing required fields
│           └─► Returns: {missing: [...], present: {...}, field_info: {...}}
│
├─► 3. CLI prompts for missing values (if any)
│       │
│       └─► For each missing field:
│           ├─► Prompt user with rich styled input
│           └─► config.set_value(key, value, field_info)
│                   ├─► If sensitive → saves to .env
│                   └─► If not → saves to .toml
│
├─► 4. CLI builds SourceConfig and calls service directly
│       │
│       └─► collection_service.create([cfg], config_service=config)
│               │
│               ├─► _build_connector_from_config(cfg, config_service)
│               │       └─► Returns: JiraCloudConnector instance
│               │
│               └─► create_collection_creator(...)
│                       │
│                       └─► DocumentCollectionCreator.run()
│                               │
│                               ├─► connector.reader.read_all_documents()
│                               │       └─► Yields documents from Jira API
│                               │
│                               ├─► connector.converter.convert(doc)
│                               │       └─► Returns: List[chunks]
│                               │
│                               ├─► indexer.index_texts(ids, texts)
│                               │       └─► Embeds and stores in FAISS
│                               │
│                               └─► persister.save_*()
│                                       └─► Writes to ./data/collections/
│
└─► 5. CLI displays success message
        └─► "✓ Collection 'jira' created with N documents"
```

## Data Flow: Search Pipeline

```
User Command: indexed index search "authentication flow"
│
├─► 1. CLI loads config
│
├─► 2. CLI calls SearchService.search()
│       │
│       └─► SearchService.search("authentication flow", top_k=10)
│               │
│               ├─► _get_or_create_searcher(collection)
│               │       ├─► Loads FAISS index from disk
│               │       └─► Returns: DocumentCollectionSearcher
│               │
│               ├─► searcher.search(query, max_results)
│               │       │
│               │       ├─► indexer.search(query_text, k)
│               │       │       ├─► Embed query with SentenceEmbedder
│               │       │       └─► FAISS similarity search
│               │       │
│               │       └─► Build SearchResult objects
│               │
│               └─► Returns: List[SearchResult]
│
└─► 3. CLI formats and displays results with Rich
```

## Configuration System

### Architecture

**Single Source of Truth**: `indexed-config` package provides unified configuration management with automatic .env loading and generic validation.

```
Config Sources (Priority: Low → High)
├── Pydantic Model Defaults
├── Global Config (~/.config/indexed/config.toml)
├── Workspace Config (./.indexed/config.toml)
├── Environment Variables (.env files)
│   ├── Project root .env (highest priority)
│   ├── Workspace .indexed/.env
│   └── Global ~/.indexed/.env
└── Environment Variables (INDEXED__*)

                ↓

        ConfigService
        ├── register(spec, path)
        ├── bind() → Provider
        ├── validate_requirements(config_class, namespace, cli_overrides)
        ├── set_value(key, value, field_info) → .toml or .env
        ├── set(path, value) → .toml only
        ├── delete(path)
        └── validate()

                ↓

          Provider
          ├── get(Type[T]) → T
          └── get_by_path(str) → BaseModel
```

### Core Principles

1. **Explicit Registration**: Components register their own config specs at usage point
2. **Zero Coupling**: Config doesn't know about consumers - it's completely generic
3. **Type Safety**: Pydantic validation throughout with introspection
4. **Version Awareness**: Namespaced paths support multiple versions (`core.v1.*`, `core.v2.*`)
5. **Generic Validation**: ConfigService works with ANY Pydantic model through field introspection
6. **Automatic .env Management**: Sensitive values (tokens, passwords) automatically saved to .env

### Usage Pattern

**Generic Validation Pattern (Recommended)**:
```python
from indexed_config import ConfigService
from connectors.jira import JiraCloudConfig

# Initialize config (auto-loads .env)
config = ConfigService()

# Validate requirements using Pydantic model introspection
validation = config.validate_requirements(
    config_class=JiraCloudConfig,
    namespace="sources.jira_cloud",
    cli_overrides={"url": "https://company.atlassian.net"}
)

# Check what's missing and prompt user
if validation["missing"]:
    for field_name in validation["missing"]:
        field_info = validation["field_info"][field_name]
        value = prompt_user(field_name)
        
        # ConfigService automatically saves to .env or .toml based on sensitivity
        config.set_value(
            f"sources.jira_cloud.{field_name}",
            value,
            field_info=field_info
        )

# All values now available in validation["present"]
```

### Field Metadata Convention

```python
from pydantic import BaseModel, Field

class MyConnectorConfig(BaseModel):
    # Non-sensitive, stored in .toml
    url: str = Field(..., description="Server URL")
    
    # Non-sensitive with env var, stored in .toml
    email: Optional[str] = Field(
        None,
        description="Email (env: MY_EMAIL)",
        json_schema_extra={"env_var": "MY_EMAIL"}
    )
    
    # Sensitive, stored in .env
    api_token: Optional[str] = Field(
        None,
        description="API token (env: MY_TOKEN)",
        json_schema_extra={
            "sensitive": True,
            "env_var": "MY_TOKEN"
        }
    )
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

## Extension Points

### 1. Adding a New Connector

Implement the BaseConnector protocol:

```python
from core.v1.connectors.base import BaseConnector
from core.v1.connectors.metadata import ConnectorMetadata

class GitConnector:
    META: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        name="git",
        display_name="Git Repository",
        description="Index files from a Git repository",
        config_class=GitConfig,
        version="1.0.0",
        min_core_version="1.0.0",
    )
    
    def __init__(self, repo_url: str, branch: str = "main"):
        self._reader = GitDocumentReader(repo_url, branch)
        self._converter = GitDocumentConverter()
    
    @property
    def reader(self) -> GitDocumentReader:
        return self._reader
    
    @property
    def converter(self) -> GitDocumentConverter:
        return self._converter
    
    @property
    def connector_type(self) -> str:
        return "git"
    
    @classmethod
    def from_dto(cls, config: GitConfig) -> "GitConnector":
        return cls(repo_url=config.url, branch=config.branch)
```

### 2. Adding a New Embedding Provider

```python
class OpenAIEmbedder:
    def __init__(self, model: str = "text-embedding-3-small"):
        self.model = model
        self.client = OpenAI()
    
    def embed_text(self, text: str) -> np.ndarray:
        response = self.client.embeddings.create(
            model=self.model,
            input=text
        )
        return np.array(response.data[0].embedding)
    
    def embed_batch(self, texts: List[str]) -> np.ndarray:
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        return np.array([d.embedding for d in response.data])
```

### 3. Swapping Vector Store

```python
class QdrantIndexer:
    def __init__(self, collection_name: str, embedder):
        self.client = QdrantClient(...)
        self.embedder = embedder
    
    def index_texts(self, ids: List[int], texts: List[str]):
        embeddings = self.embedder.embed_batch(texts)
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(id=id, vector=emb.tolist())
                for id, emb in zip(ids, embeddings)
            ]
        )
    
    def search(self, text: str, k: int) -> Tuple[np.ndarray, np.ndarray]:
        embedding = self.embedder.embed_text(text)
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=embedding.tolist(),
            limit=k
        )
        # Return (scores, indices) to match FAISS interface
        ...
```

## Storage Architecture

### Directory Structure

```
./data/                          # Data root
├── collections/                 # Collection storage
│   └── {collection_name}/
│       ├── documents/           # Document metadata
│       │   └── *.json
│       ├── manifest.json        # Collection manifest
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

## Key Design Principles

1. **KISS (Keep It Simple)**: Facade pattern over complex layering
2. **Separation of Concerns**: Each component has single responsibility
3. **Protocol-Based Design**: BaseConnector enables extensibility
4. **Configuration over Code**: Behavior controlled by config files
5. **Testability**: Services have clear interfaces, easy to mock
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
