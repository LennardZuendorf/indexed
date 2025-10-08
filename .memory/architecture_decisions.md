# Architecture Decisions

## Overview

This document captures key architectural decisions for the Indexed project.

## Decision 1: Versioned API with Config Isolation

**Date**: 2025-10-08  
**Status**: ✅ Approved

### Problem
Config structure will evolve over time. Without versioning, changes break backward compatibility and TOML files become cluttered with conflicting configurations.

### Solution
Version the API and config together:

```
packages/indexed-core/src/core/
├── v1/
│   ├── __init__.py       # Exports: Index, Config, Connectors
│   ├── index.py          # Main Index class
│   ├── config.py         # V1-specific config
│   ├── connectors.py     # Connector classes (exported)
│   ├── storage.py        
│   └── embeddings.py     
└── v2/ (future)
    ├── __init__.py       # Different API, different config
    └── ...
```

**Config Structure**:
```toml
# indexed.toml
[indexer.v1]
embedding_model = "all-MiniLM-L6-v2"
storage_path = ".indexed/v1"  # Versioned storage path!
chunk_size = 512

# Future: [indexer.v2] with completely different structure
[indexer.v2]
embedding_provider = "openai"  # Different keys, no conflicts
workspace_path = ".indexed/v2"
```

**Benefits**:
- ✅ No config conflicts between versions
- ✅ Storage paths automatically isolated (`.indexed/v1/`, `.indexed/v2/`)
- ✅ Can run v1 and v2 side-by-side
- ✅ Config logic lives with the code it configures
- ✅ Clear upgrade path

**Usage**:
```python
from core.v1 import Index, Config
from core.v1.connectors import JiraConnector, FileSystemConnector

# Initialize with config
config = Config.from_file("indexed.toml")  # Reads [indexer.v1]
index = Index(config)

# Add collections
jira_connector = JiraConnector(config)
index.add_collection(jira_connector, name="jira")

files_connector = FileSystemConnector('./docs')
index.add_collection(files_connector, name="docs")

# Search specific collection
results = index.search(collection="jira", query="What was project xyz?")

# Search all collections
results = index.search(query="authentication methods")

# Update a collection
index.update(collection="jira")

# List all collections
collections = index.list_collections()  # ["jira", "docs"]
```

---

## Decision 2: Dual CLI Structure

**Date**: 2025-10-08  
**Status**: ✅ Approved

### Problem
Mixing document operations with configuration management in a single command group creates confusion and poor UX.

### Solution
Separate CLI into two command groups:

**Index CLI** - Collection operations:
```bash
# Collection management
indexed-cli add files ./docs --name docs      # Add file collection
indexed-cli add jira --name jira              # Add Jira collection (uses config)
indexed-cli list                              # List all collections
indexed-cli remove docs                       # Remove a collection

# Search operations
indexed-cli search "query"                    # Search all collections
indexed-cli search "query" --collection jira  # Search specific collection

# Maintenance
indexed-cli update jira                       # Update specific collection
indexed-cli inspect                           # Show all stats
indexed-cli inspect --collection docs         # Show collection stats
```

**Config CLI** - Configuration management:
```bash
indexed-cli config init       # Create indexed.toml
indexed-cli config show       # Display current config
indexed-cli config set KEY VALUE
indexed-cli config validate   # Validate config file
indexed-cli config path       # Show config location
```

**Implementation**:
```
apps/indexed-cli/src/cli/
├── app.py           # Main CLI entry (Typer app)
├── index_cli.py     # Index command group
└── config_cli.py    # Config command group
```

**Benefits**:
- ✅ Clear separation of concerns
- ✅ Better discoverability (`--help` is cleaner)
- ✅ Config operations isolated and explicit
- ✅ Easy to add more command groups later (e.g., `admin`)

---

## Decision 3: Simple Indexer Class (Not Over-Engineered)

**Date**: 2025-10-08  
**Status**: ✅ Approved

### Problem
Need good structure without over-engineering (no factories, no complex DI).

### Solution
Single `Indexer` class that coordinates simple service classes:

```python
# core/v1/index.py
class Index:
    """Main entry point for V1 indexing API - manages multiple collections"""
    
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self._storage = Storage(self.config)
        self._embeddings = EmbeddingService(self.config)
        self._collections = {}  # name -> collection metadata
    
    def add_collection(self, connector, name: str, **kwargs) -> CollectionStats:
        """Add/create a new collection from a connector"""
        docs = connector.read()
        vectors = self._embeddings.embed(docs)
        stats = self._storage.store_collection(name, vectors, **kwargs)
        self._collections[name] = {"connector": connector, "stats": stats}
        return stats
    
    def search(self, query: str, collection: str | None = None, top_k: int = 10) -> List[SearchResult]:
        """Search collections
        
        Args:
            query: Search query
            collection: Specific collection name, or None to search all
            top_k: Number of results to return
        """
        query_vector = self._embeddings.embed(query)
        
        if collection:
            # Search specific collection
            results = self._storage.search_collection(collection, query_vector, top_k)
        else:
            # Search all collections
            results = self._storage.search_all(query_vector, top_k)
        
        return results
    
    def update(self, collection: str) -> UpdateStats:
        """Update/re-index a specific collection"""
        coll_info = self._collections[collection]
        connector = coll_info["connector"]
        # Re-read and re-embed
        docs = connector.read()
        vectors = self._embeddings.embed(docs)
        stats = self._storage.update_collection(collection, vectors)
        return stats
    
    def remove_collection(self, name: str) -> None:
        """Remove a collection"""
        self._storage.delete_collection(name)
        del self._collections[name]
    
    def list_collections(self) -> List[str]:
        """List all collection names"""
        return list(self._collections.keys())
    
    def inspect(self, collection: str | None = None) -> IndexStats:
        """Get statistics for specific collection or all"""
        if collection:
            return self._storage.get_collection_stats(collection)
        return self._storage.get_all_stats()
```

**What We Avoid**:
- ❌ Factory pattern - just `Index()`
- ❌ Dependency injection framework - just pass config
- ❌ Abstract base classes - unless truly needed
- ❌ Complex interfaces - just simple classes

**What We Keep**:
- ✅ Basic separation of concerns (storage, embeddings, connectors)
- ✅ Testable (can mock the internal services)
- ✅ Type hints for clarity
- ✅ Pydantic for config validation

**Exported API**:
```python
from core.v1 import Index, Config, Connectors

index = Index()                      # Main class
config = Config.from_file()          # Config management
connector = Connectors.JiraConnector() # Direct connector access
```

**Philosophy**: KISS first. Add patterns only when complexity demands it.

---

## Decision 4: Package Structure in Monorepo

**Date**: 2025-10-08  
**Status**: ✅ Approved

### Structure
```
indexed/
├── apps/
│   └── indexed-cli/         # CLI application
│       ├── src/cli/
│       │   ├── app.py
│       │   ├── index_cli.py
│       │   └── config_cli.py
│       └── pyproject.toml
├── packages/
│   ├── indexed-core/        # Core V1 API
│   │   └── src/core/v1/
│   │       ├── __init__.py  # Exports: Index, Config, Connectors
│   │       ├── index.py     # Main Index class
│   │       ├── config.py    # Config class
│   │       ├── connectors.py # Connector classes
│   │       ├── storage.py   # Internal: FAISS storage
│   │       └── embeddings.py # Internal: Embeddings
│   ├── indexed-connectors/  # Shared connector implementations
│   └── utils/              # Shared utilities
└── pyproject.toml          # Workspace root
```

**Import Pattern**:
```python
# In CLI
from core.v1 import Index, Config, Connectors

# Main operations
index = Index()
index.embed('./docs')
results = index.search('query')

# Config management
config = Config.from_file('indexed.toml')

# Direct connector usage (advanced)
connector = Connectors.FileSystemConnector('./docs')
docs = connector.read()
```

**Benefits**:
- ✅ Clean namespace (`core.v1` not `indexed_core.v1`)
- ✅ Three clear exports: `Index`, `Config`, `Connectors`
- ✅ Workspace dependencies managed by UV
- ✅ Easy to add v2 alongside v1
- ✅ Core is importable by anyone

---

## Future Decisions (To Be Made)

### When to Add V2?
- When API needs significant changes
- When config structure needs to change
- Not before v1 is stable and working

### When to Add Server UI?
- After CLI with Rich enhancements is stable
- After v1 API is proven and tested
- Likely in separate `apps/indexed-server/` package

### When to Add Complex Patterns?
- Only when simple patterns cause pain
- Document the pain point first
- Consider KISS alternatives before adding complexity

---

**Remember**: Start simple. Add complexity only when needed. Document why.