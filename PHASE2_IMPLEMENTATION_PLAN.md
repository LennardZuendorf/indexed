# Phase 2 Implementation Plan: Controller/Service Architecture

## Overview
Transform indexed-python into a clean, layered architecture with proper separation of concerns, dependency injection, and configuration management. This phase implements the Controller/Service pattern validated against LlamaIndex best practices.

## Architecture Principles

### 1. Layered Architecture
```
CLI Layer (indexed-cli)
    ↓
Controllers (orchestration)
    ↓
Services (business logic)
    ↓
Storage/Connectors (infrastructure)
```

### 2. Dependency Injection
- Constructor injection throughout
- CLI acts as composition root
- Configuration-driven instantiation
- Testable, mockable dependencies

### 3. Configuration-First Design
- TOML-based configuration
- Pydantic models for validation
- Global and workspace-level configs
- Sensible defaults

## Directory Structure

```
packages/indexed-core/src/indexed_core/
├── config/
│   ├── __init__.py
│   ├── models.py          # Pydantic config models
│   ├── service.py         # ConfigService for loading/saving
│   └── default_config.toml
├── models/
│   ├── __init__.py
│   └── document.py        # Document, Chunk, SearchResult
├── connectors/
│   ├── __init__.py
│   ├── base.py            # DocumentConnector protocol
│   └── filesystem.py      # FileSystemConnector implementation
├── storage/
│   ├── __init__.py
│   └── base.py            # Optional: Vector store abstraction
├── services/
│   ├── __init__.py
│   ├── storage.py         # StorageService (FAISS wrapper)
│   ├── embedding.py       # EmbeddingService (sentence-transformers)
│   ├── indexing.py        # IndexingService (orchestrates indexing)
│   └── search.py          # SearchService (semantic search)
├── controllers/
│   ├── __init__.py
│   ├── index_controller.py   # High-level indexing operations
│   └── search_controller.py  # High-level search operations
├── factory.py             # Service instantiation & DI
└── legacy/                # Existing legacy code (Phase 1)
```

## Configuration Schema

### TOML Structure
```toml
[workspace]
name = "my-workspace"
root_path = "/path/to/workspace"
index_path = "${root_path}/.indexed"

[embedding]
provider = "sentence-transformers"
model_name = "all-MiniLM-L6-v2"
dimension = 384
batch_size = 32

[vector_store]
type = "faiss"
index_type = "IndexFlatL2"  # or IndexIVFFlat
persistence_enabled = true
persistence_path = "${workspace.index_path}/faiss_index"

[indexing]
chunk_size = 512
chunk_overlap = 50
exclude_patterns = ["*.pyc", "__pycache__", ".git"]
include_patterns = ["*.py", "*.md", "*.txt"]

[connectors.filesystem]
enabled = true
watch_for_changes = false

[connectors.git]
enabled = false
# Future: git-specific settings

[search]
default_top_k = 10
similarity_threshold = 0.7
```

### Pydantic Models (config/models.py)

```python
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional, List

class WorkspaceConfig(BaseModel):
    name: str = "default"
    root_path: Path
    index_path: Optional[Path] = None
    
    def __post_init__(self):
        if not self.index_path:
            self.index_path = self.root_path / ".indexed"

class EmbeddingConfig(BaseModel):
    provider: str = "sentence-transformers"
    model_name: str = "all-MiniLM-L6-v2"
    dimension: int = 384
    batch_size: int = 32
    device: Optional[str] = None  # "cpu", "cuda", "mps"

class VectorStoreConfig(BaseModel):
    type: str = "faiss"
    index_type: str = "IndexFlatL2"
    persistence_enabled: bool = True
    persistence_path: Optional[Path] = None

class IndexingConfig(BaseModel):
    chunk_size: int = 512
    chunk_overlap: int = 50
    exclude_patterns: List[str] = Field(default_factory=lambda: ["*.pyc", "__pycache__", ".git"])
    include_patterns: List[str] = Field(default_factory=lambda: ["*.py", "*.md", "*.txt"])

class ConnectorConfig(BaseModel):
    filesystem_enabled: bool = True
    filesystem_watch: bool = False
    git_enabled: bool = False

class SearchConfig(BaseModel):
    default_top_k: int = 10
    similarity_threshold: float = 0.7

class IndexedConfig(BaseModel):
    """Root configuration model."""
    workspace: WorkspaceConfig
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    connectors: ConnectorConfig = Field(default_factory=ConnectorConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
```

## Component Specifications

### 1. Config Service (config/service.py)

```python
class ConfigService:
    """Loads, validates, and saves configuration."""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self._default_config_path()
    
    def load_config(self) -> IndexedConfig:
        """Load and validate config from TOML."""
        # Load from file or use defaults
        # Validate with Pydantic
        # Return typed config
        
    def save_config(self, config: IndexedConfig) -> None:
        """Save config to TOML file."""
        
    def merge_configs(self, global_config: dict, workspace_config: dict) -> dict:
        """Merge workspace-level config with global defaults."""
    
    @staticmethod
    def _default_config_path() -> Path:
        """Returns ~/.indexed/config.toml or workspace .indexed/config.toml"""
```

### 2. Domain Models (models/document.py)

```python
from dataclasses import dataclass
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime

@dataclass
class Document:
    """Represents a source document."""
    id: str
    content: str
    source_path: Path
    metadata: Dict[str, Any]
    created_at: datetime
    
@dataclass
class Chunk:
    """Represents a chunk of a document."""
    id: str
    document_id: str
    content: str
    index: int  # Chunk index within document
    metadata: Dict[str, Any]

@dataclass
class SearchResult:
    """Represents a search result."""
    chunk: Chunk
    score: float
    document: Optional[Document] = None
```

### 3. Connectors (connectors/base.py)

```python
from typing import Protocol, List, Iterator
from pathlib import Path
from models.document import Document

class DocumentConnector(Protocol):
    """Interface for document connectors."""
    
    def discover_documents(self, source: str) -> Iterator[Path]:
        """Discover documents from a source."""
        ...
    
    def read_document(self, path: Path) -> Document:
        """Read and parse a document."""
        ...
    
    def supports_path(self, path: Path) -> bool:
        """Check if this connector supports the given path."""
        ...
```

**FileSystemConnector Implementation:**
```python
class FileSystemConnector:
    """Reads documents from filesystem."""
    
    def __init__(self, 
                 include_patterns: List[str],
                 exclude_patterns: List[str]):
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
    
    def discover_documents(self, source: str) -> Iterator[Path]:
        """Recursively discover files matching patterns."""
        # Use glob patterns
        # Apply include/exclude filters
        
    def read_document(self, path: Path) -> Document:
        """Read file content and create Document."""
        # Use unstructured or simple file reading
        # Extract metadata (size, modified date, etc.)
```

### 4. Services Layer

#### StorageService (services/storage.py)
```python
import faiss
import numpy as np
from pathlib import Path

class StorageService:
    """Manages vector storage with FAISS."""
    
    def __init__(self, 
                 dimension: int,
                 index_type: str = "IndexFlatL2",
                 persistence_path: Optional[Path] = None):
        self.dimension = dimension
        self.persistence_path = persistence_path
        self.index = self._create_index(index_type)
        self.id_mapping: Dict[int, str] = {}  # Vector index -> Chunk ID
        
    def add_vectors(self, vectors: np.ndarray, ids: List[str]) -> None:
        """Add vectors to index."""
        
    def search(self, query_vector: np.ndarray, top_k: int) -> List[Tuple[str, float]]:
        """Search for similar vectors."""
        # Returns [(chunk_id, similarity_score), ...]
        
    def delete_by_ids(self, ids: List[str]) -> None:
        """Remove vectors by chunk IDs."""
        
    def save(self) -> None:
        """Persist index to disk."""
        
    def load(self) -> None:
        """Load index from disk."""
```

#### EmbeddingService (services/embedding.py)
```python
from sentence_transformers import SentenceTransformer

class EmbeddingService:
    """Generates embeddings using sentence-transformers."""
    
    def __init__(self, 
                 model_name: str,
                 device: Optional[str] = None,
                 batch_size: int = 32):
        self.model = SentenceTransformer(model_name, device=device)
        self.batch_size = batch_size
        
    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text."""
        
    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Embed multiple texts efficiently."""
        
    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return self.model.get_sentence_embedding_dimension()
```

#### IndexingService (services/indexing.py)
```python
class IndexingService:
    """Orchestrates document indexing pipeline."""
    
    def __init__(self,
                 connectors: List[DocumentConnector],
                 embedding_service: EmbeddingService,
                 storage_service: StorageService,
                 chunk_size: int = 512,
                 chunk_overlap: int = 50):
        self.connectors = connectors
        self.embedding_service = embedding_service
        self.storage_service = storage_service
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
    def index_source(self, source: str) -> int:
        """Index documents from a source."""
        # 1. Use connectors to discover documents
        # 2. Read documents
        # 3. Chunk documents
        # 4. Generate embeddings
        # 5. Store in vector store
        # Return: number of chunks indexed
        
    def reindex(self, source: str) -> int:
        """Remove old index and rebuild."""
        
    def _chunk_document(self, document: Document) -> List[Chunk]:
        """Split document into chunks."""
```

#### SearchService (services/search.py)
```python
class SearchService:
    """Handles semantic search queries."""
    
    def __init__(self,
                 embedding_service: EmbeddingService,
                 storage_service: StorageService):
        self.embedding_service = embedding_service
        self.storage_service = storage_service
        
    def search(self, query: str, top_k: int = 10) -> List[SearchResult]:
        """Perform semantic search."""
        # 1. Embed query
        # 2. Search vector store
        # 3. Retrieve chunks and documents
        # 4. Format results
```

### 5. Controllers

#### IndexController (controllers/index_controller.py)
```python
class IndexController:
    """High-level indexing operations."""
    
    def __init__(self, 
                 indexing_service: IndexingService,
                 storage_service: StorageService):
        self.indexing_service = indexing_service
        self.storage_service = storage_service
        
    def create_index(self, sources: List[str]) -> Dict[str, Any]:
        """Create a new index from sources."""
        # Returns stats: {chunks_indexed, documents_processed, time_taken}
        
    def update_index(self, sources: List[str]) -> Dict[str, Any]:
        """Incrementally update existing index."""
        
    def rebuild_index(self, sources: List[str]) -> Dict[str, Any]:
        """Completely rebuild index."""
        
    def get_index_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
```

#### SearchController (controllers/search_controller.py)
```python
class SearchController:
    """High-level search operations."""
    
    def __init__(self, search_service: SearchService):
        self.search_service = search_service
        
    def search(self, query: str, **options) -> List[SearchResult]:
        """Execute semantic search."""
        
    def search_with_filters(self, 
                           query: str, 
                           filters: Dict[str, Any],
                           **options) -> List[SearchResult]:
        """Search with metadata filters."""
```

### 6. Factory Pattern (factory.py)

```python
class ServiceFactory:
    """Factory for creating services from configuration."""
    
    @staticmethod
    def create_from_config(config: IndexedConfig) -> tuple:
        """
        Create all services and controllers from config.
        
        Returns: (index_controller, search_controller, config)
        """
        # 1. Create EmbeddingService
        embedding_service = EmbeddingService(
            model_name=config.embedding.model_name,
            device=config.embedding.device,
            batch_size=config.embedding.batch_size
        )
        
        # 2. Create StorageService
        storage_service = StorageService(
            dimension=embedding_service.dimension,
            index_type=config.vector_store.index_type,
            persistence_path=config.vector_store.persistence_path
        )
        
        # 3. Create connectors
        connectors = []
        if config.connectors.filesystem_enabled:
            connectors.append(FileSystemConnector(
                include_patterns=config.indexing.include_patterns,
                exclude_patterns=config.indexing.exclude_patterns
            ))
        
        # 4. Create IndexingService
        indexing_service = IndexingService(
            connectors=connectors,
            embedding_service=embedding_service,
            storage_service=storage_service,
            chunk_size=config.indexing.chunk_size,
            chunk_overlap=config.indexing.chunk_overlap
        )
        
        # 5. Create SearchService
        search_service = SearchService(
            embedding_service=embedding_service,
            storage_service=storage_service
        )
        
        # 6. Create Controllers
        index_controller = IndexController(
            indexing_service=indexing_service,
            storage_service=storage_service
        )
        
        search_controller = SearchController(
            search_service=search_service
        )
        
        return index_controller, search_controller, config
```

### 7. CLI Integration (indexed-cli)

```python
# In indexed-cli/src/indexed_cli/commands/create.py

import typer
from indexed_core.config import ConfigService
from indexed_core.factory import ServiceFactory

def create_index(path: str, workspace_name: str = "default"):
    """Create a new index."""
    # 1. Load configuration
    config_service = ConfigService()
    config = config_service.load_config()
    
    # 2. Create services via factory
    index_controller, _, _ = ServiceFactory.create_from_config(config)
    
    # 3. Use controller
    result = index_controller.create_index(sources=[path])
    
    # 4. Display results
    typer.echo(f"Indexed {result['chunks_indexed']} chunks from {result['documents_processed']} documents")
```

## Implementation Order

### Phase 2.1: Foundation (Steps 1-4)
1. ✅ Define Pydantic config models
2. ✅ Implement ConfigService
3. ✅ Define base interfaces
4. ✅ Create domain models

### Phase 2.2: Core Services (Steps 5-7)
5. ✅ Implement StorageService
6. ✅ Implement EmbeddingService
7. ✅ Implement FileSystemConnector

### Phase 2.3: Business Logic (Steps 8-11)
8. ✅ Implement IndexingService
9. ✅ Implement SearchService
10. ✅ Implement IndexController
11. ✅ Implement SearchController

### Phase 2.4: Integration (Steps 12-15)
12. ✅ Create ServiceFactory
13. ✅ Create default config template
14. ✅ Add comprehensive tests
15. ✅ Update CLI to use new architecture

## Testing Strategy

### Unit Tests
- Test each service in isolation with mocked dependencies
- Test config loading/validation with various TOML inputs
- Test connectors with temporary file structures

### Integration Tests
- Test full indexing pipeline from file to vector store
- Test search end-to-end
- Test configuration-driven instantiation

### Test Structure
```
packages/indexed-core/tests/
├── unit/
│   ├── test_config_service.py
│   ├── test_embedding_service.py
│   ├── test_storage_service.py
│   ├── test_indexing_service.py
│   ├── test_search_service.py
│   └── test_controllers.py
├── integration/
│   ├── test_indexing_pipeline.py
│   └── test_search_pipeline.py
└── fixtures/
    ├── sample_documents/
    └── test_configs/
```

## Migration Path from Legacy

### Parallel Operation
- Keep legacy code functional during Phase 2
- New CLI commands use new architecture
- Legacy commands remain for compatibility

### Deprecation Strategy
- Phase 2: New commands available, legacy commands deprecated
- Phase 3: Legacy code removed, migration guide provided

## Success Criteria

- ✅ Clean separation of concerns (config, services, controllers)
- ✅ All dependencies injected, not hardcoded
- ✅ Configuration-driven instantiation
- ✅ Pluggable connectors (easy to add Git, Notion, etc.)
- ✅ Pluggable embedding models (config change only)
- ✅ Pluggable vector stores (easy to swap FAISS for Weaviate/Qdrant)
- ✅ Comprehensive unit and integration tests
- ✅ CLI commands use new architecture
- ✅ Documentation updated

## Future Extensibility

### Adding New Connectors
```python
# Just implement DocumentConnector protocol
class GitConnector:
    def discover_documents(self, source: str) -> Iterator[Path]:
        # Clone repo, discover files
        
    def read_document(self, path: Path) -> Document:
        # Read from git tree
```

### Changing Vector Store
```python
# Update config
[vector_store]
type = "qdrant"
url = "http://localhost:6333"

# Add QdrantStorageService implementing same interface
# Factory will instantiate correct one based on config
```

### Changing Embedding Model
```python
# Just update config
[embedding]
provider = "openai"
model_name = "text-embedding-3-small"
api_key = "${OPENAI_API_KEY}"
```

## Dependencies to Add

```toml
# Already have:
# - faiss-cpu
# - sentence-transformers
# - pydantic-settings

# May need:
toml = "^0.10.2"  # For TOML parsing (or use tomli/tomllib)
```

## Notes

- Use `platformdirs` for config path detection (already a dependency)
- Use `pydantic-settings` for environment variable interpolation in config
- Keep LlamaIndex integration optional for now (can add later if needed)
- Focus on FAISS first; other vector stores are future enhancements
- Document all public APIs with docstrings
- Use type hints throughout

---

**Ready to implement?** Start with Phase 2.1 (Foundation) and proceed step by step!
