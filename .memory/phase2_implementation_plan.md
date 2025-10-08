# Phase 2 Implementation Plan: Core API Standardization

**Status:** 🟢 Active - Task 1 Complete ✅  
**Started:** 2025-10-08  
**Goal:** Clean, simple API with `Index`, `Config` classes and standardized connectors

## Progress

✅ **Task 1 Complete (2025-10-08):** Core API Classes Created
- `core/v1/core_config.py` - Config class with Pydantic
- `core/v1/index.py` - Index class wrapping services
- `core/v1/__init__.py` - Public exports
- Tested and working: `from core.v1 import Index, Config`

---

## Current State Analysis

### What We Have ✅
```
packages/indexed-core/src/core/v1/engine/
├── services/
│   ├── collection_service.py    # create(), update(), clear()
│   ├── search_service.py        # search(), SearchService class
│   ├── inspect_service.py       # status()
│   ├── config_service.py        # ConfigService, get_config(), etc.
│   └── models.py                # SourceConfig, CollectionStatus, SearchResult
├── indexes/
│   ├── indexers/faiss_indexer.py
│   └── embeddings/sentence_embeder.py
└── persisters/disk_persister.py

packages/indexed-connectors/src/connectors/
├── jira/                        # Jira connector
├── confluence/                  # Confluence connector  
└── files/                       # File system connector
```

### Current API (Functional but Complex)
```python
# Current usage in CLI
from core.v1.engine.services import create, search, status, SourceConfig

config = SourceConfig(name="docs", type="localFiles", base_url_or_path="./docs", indexer="...")
create([config])
results = search("query", configs=[config])
statuses = status(["docs"])
```

---

## Target State: Simple & Clean API

### Target API Design
```python
# High-level API - Simple for most users
from indexed.v1 import Index, Config

# Create index instance
index = Index(config=Config.load())  # or Config.from_file("indexed.toml")

# Add collections
index.add_collection("docs", connector="filesystem", path="./docs")
index.add_collection("jira", connector="jira", url="...", query="...")

# Operations
results = index.search("query")                      # All collections
results = index.search("query", collection="docs")   # Specific collection
index.update("docs")                                 # Update specific collection
status = index.status()                              # All collections status
status = index.status("docs")                        # Single collection status

# Configuration
config = Config.load()  # From indexed.toml or defaults
config.embedding_model = "all-MiniLM-L6-v2"
config.chunk_size = 512
config.save()  # Save to indexed.toml
```

### Connector API (Standardized)
```python
# Protocol-based connector interface
from indexed.v1.connectors import FileSystemConnector, JiraConnector, ConfluenceConnector

# All connectors implement same interface
connector = FileSystemConnector(base_path="./docs")
for doc in connector.discover():
    content = connector.read(doc.id)
    metadata = connector.get_metadata(doc.id)
```

---

## Implementation Tasks

### Task 1: Create Core API Classes (Week 1, Days 1-2)

**File:** `packages/indexed-core/src/core/v1/index.py`

```python
"""Main Index class for managing document collections."""

from typing import Optional, List, Dict, Any
from .config import Config
from .connectors import get_connector
from .engine.services import create, update, search, status, clear, SourceConfig

class Index:
    """Main interface for indexed document search.
    
    Examples:
        >>> index = Index()
        >>> index.add_collection("docs", connector="filesystem", path="./docs")
        >>> results = index.search("authentication methods")
    """
    
    def __init__(self, config: Optional[Config] = None):
        """Initialize index with optional configuration."""
        self.config = config or Config.load()
        self._collections: Dict[str, SourceConfig] = {}
    
    def add_collection(
        self,
        name: str,
        connector: str,
        **connector_params
    ) -> None:
        """Add a new collection to the index.
        
        Args:
            name: Collection name
            connector: Connector type (filesystem, jira, confluence)
            **connector_params: Connector-specific parameters
        """
        # Create SourceConfig from connector params
        source_config = self._create_source_config(name, connector, connector_params)
        
        # Create the collection
        create([source_config], use_cache=True, force=False)
        
        # Track it
        self._collections[name] = source_config
    
    def search(
        self,
        query: str,
        collection: Optional[str] = None,
        max_results: int = 10
    ) -> Dict[str, Any]:
        """Search across collections.
        
        Args:
            query: Search query
            collection: Optional specific collection name
            max_results: Maximum number of results
            
        Returns:
            Dictionary with collection results
        """
        if collection:
            configs = [self._collections[collection]]
        else:
            configs = None  # Auto-discover all
        
        return search(
            query,
            configs=configs,
            max_docs=max_results,
            max_chunks=max_results * 3
        )
    
    def update(self, collection: Optional[str] = None) -> None:
        """Update collections with new documents.
        
        Args:
            collection: Specific collection or None for all
        """
        if collection:
            update([self._collections[collection]])
        else:
            # Update all collections
            for config in self._collections.values():
                update([config])
    
    def status(self, collection: Optional[str] = None):
        """Get status of collections.
        
        Args:
            collection: Specific collection or None for all
            
        Returns:
            CollectionStatus or List[CollectionStatus]
        """
        if collection:
            return status([collection])[0]
        else:
            return status()
    
    def remove(self, collection: str) -> None:
        """Remove a collection.
        
        Args:
            collection: Collection name to remove
        """
        clear([collection])
        if collection in self._collections:
            del self._collections[collection]
    
    def list_collections(self) -> List[str]:
        """List all collection names."""
        return list(self._collections.keys())
    
    def _create_source_config(
        self, name: str, connector: str, params: Dict
    ) -> SourceConfig:
        """Create SourceConfig from connector params."""
        # Map connector types to SourceConfig types
        connector_map = {
            "filesystem": "localFiles",
            "jira": "jira",
            "jiracloud": "jiraCloud",
            "confluence": "confluence",
            "confluencecloud": "confluenceCloud",
        }
        
        source_type = connector_map.get(connector.lower(), connector)
        
        # Extract common params
        base_url_or_path = params.get("path") or params.get("url") or params.get("base_path")
        query = params.get("query") or params.get("jql") or params.get("cql")
        
        return SourceConfig(
            name=name,
            type=source_type,
            base_url_or_path=base_url_or_path,
            query=query,
            indexer=self.config.default_indexer,
            reader_opts=params.get("reader_opts", {})
        )
```

**File:** `packages/indexed-core/src/core/v1/config.py`

```python
"""Configuration management for indexed."""

from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

class Config(BaseModel):
    """Main configuration for indexed.
    
    Examples:
        >>> config = Config.load()
        >>> config.embedding_model = "all-MiniLM-L6-v2"
        >>> config.save()
    """
    
    # Embedding configuration
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Embedding model to use"
    )
    
    # Indexing configuration
    chunk_size: int = Field(default=512, description="Text chunk size")
    chunk_overlap: int = Field(default=50, description="Overlap between chunks")
    batch_size: int = Field(default=32, description="Batch size for processing")
    
    # Search configuration
    default_max_results: int = Field(default=10, description="Default max results")
    similarity_threshold: float = Field(default=0.7, description="Similarity threshold")
    
    # Storage configuration
    storage_path: Path = Field(
        default=Path("./data/collections"),
        description="Base path for collections"
    )
    
    # Default indexer name
    default_indexer: str = Field(
        default="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
        description="Default FAISS indexer configuration"
    )
    
    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Config":
        """Load configuration from file or use defaults.
        
        Args:
            config_path: Path to indexed.toml (optional)
            
        Returns:
            Config instance
        """
        if config_path and config_path.exists():
            # TODO: Load from TOML file
            pass
        
        # For now, return defaults
        return cls()
    
    @classmethod
    def from_file(cls, path: str) -> "Config":
        """Load from specific file path."""
        return cls.load(Path(path))
    
    def save(self, path: Optional[Path] = None) -> None:
        """Save configuration to file.
        
        Args:
            path: Path to save to (default: ./indexed.toml)
        """
        save_path = path or Path("./indexed.toml")
        # TODO: Save to TOML file
        pass
```

**File:** `packages/indexed-core/src/core/v1/__init__.py`

```python
"""Indexed v1 API - Simple, clean interface."""

from .index import Index
from .config import Config

__all__ = ["Index", "Config"]
```

### Task 2: Standardize Connector Interface (Week 1, Days 3-5)

**File:** `packages/indexed-core/src/core/v1/connectors/__init__.py`

```python
"""Connector protocol and factory."""

from typing import Protocol, Iterator
from dataclasses import dataclass
from datetime import datetime

@dataclass
class DocumentMetadata:
    """Metadata for a document."""
    id: str
    title: str
    url: Optional[str]
    modified_time: datetime
    source_type: str
    extra: dict = field(default_factory=dict)

@dataclass
class Document:
    """Full document with content."""
    id: str
    title: str
    content: str
    url: Optional[str]
    modified_time: datetime
    metadata: dict = field(default_factory=dict)

class DocumentConnector(Protocol):
    """Standard interface for document connectors."""
    
    def discover(self) -> Iterator[DocumentMetadata]:
        """Discover available documents."""
        ...
    
    def read(self, doc_id: str) -> Document:
        """Read a specific document."""
        ...
    
    def test_connection(self) -> bool:
        """Test if connector can connect."""
        ...

def get_connector(connector_type: str, **params) -> DocumentConnector:
    """Factory function to get connector instance."""
    # Import connectors from indexed-connectors package
    from connectors.files import FileSystemConnector
    from connectors.jira import JiraConnector
    from connectors.confluence import ConfluenceConnector
    
    connector_map = {
        "filesystem": FileSystemConnector,
        "jira": JiraConnector,
        "confluence": ConfluenceConnector,
    }
    
    connector_class = connector_map.get(connector_type.lower())
    if not connector_class:
        raise ValueError(f"Unknown connector type: {connector_type}")
    
    return connector_class(**params)
```

### Task 3: Update CLI to Use New API (Week 2, Days 1-2)

**File:** `apps/indexed-cli/src/cli/commands/v2_create.py` (NEW)

```python
"""V2 create commands using new Index API."""

import typer
from indexed.v1 import Index, Config

v2_create_app = typer.Typer(help="Create collections (V2 API)")

@v2_create_app.command("files")
def create_files(
    name: str = typer.Option(..., "--name", "-n", help="Collection name"),
    path: str = typer.Option(..., "--path", "-p", help="Path to files"),
):
    """Create collection from local files."""
    index = Index(config=Config.load())
    
    typer.echo(f"Creating collection '{name}' from {path}...")
    index.add_collection(name, connector="filesystem", path=path)
    typer.echo(f"✅ Collection '{name}' created successfully!")

@v2_create_app.command("jira")
def create_jira(
    name: str = typer.Option(..., "--name", "-n", help="Collection name"),
    url: str = typer.Option(..., "--url", "-u", help="Jira URL"),
    jql: str = typer.Option(..., "--jql", help="JQL query"),
):
    """Create collection from Jira."""
    index = Index(config=Config.load())
    
    typer.echo(f"Creating collection '{name}' from Jira...")
    index.add_collection(name, connector="jira", url=url, query=jql)
    typer.echo(f"✅ Collection '{name}' created successfully!")
```

### Task 4: Update Connectors Package (Week 2, Days 3-5)

Refactor existing connectors in `packages/indexed-connectors/` to implement the `DocumentConnector` protocol.

---

## Migration Strategy

### Phase A: Create New API (No Breaking Changes)
1. Create `Index` and `Config` classes
2. Add new connector protocol
3. Keep existing API working

### Phase B: Add V2 Commands
1. Add `v2` command group in CLI
2. Users can try new API alongside old
3. Gather feedback

### Phase C: Deprecate Old API
1. Add deprecation warnings to old imports
2. Documentation points to new API
3. Give 2-3 months migration period

### Phase D: Remove Old API
1. Remove deprecated code
2. Clean up internals
3. Final cleanup

---

## Success Criteria

- ✅ Can create index with simple `Index()` call
- ✅ Can add collections with intuitive API
- ✅ Can search with clean interface
- ✅ All existing functionality preserved
- ✅ CLI v2 commands working
- ✅ Connectors follow standard protocol
- ✅ Documentation complete
- ✅ No breaking changes to existing users

---

## Timeline

**Week 1:** Core API classes + Connector protocol  
**Week 2:** CLI integration + Connector refactoring  
**Week 3:** Testing, documentation, cleanup

**Total:** 3 weeks

---

**Next Action:** Start with Task 1 - Create `Index` and `Config` classes
