# Phase 2: Standardization & Refactoring PRD

**Date:** 2025-10-08  
**Status:** 🟢 Active - Planning Phase  
**Priority:** High  
**Estimated Effort:** 2-3 weeks  
**Dependencies:** Phase 1 Complete ✅

---

## 📋 Problem Statement

Phase 1 successfully established a monorepo structure with working CLI and MCP functionality. However, the current implementation has several inconsistencies:

### Current Issues

1. **Config Management Inconsistency**
   - Multiple config approaches (TOML files, env vars, hardcoded defaults)
   - No single source of truth for configuration
   - Config scattered across different modules
   - Difficult to understand what can be configured

2. **Connector Interface Fragmentation**
   - Different connectors have different APIs
   - No standard protocol for document readers
   - Hard to add new data sources
   - Inconsistent error handling

3. **Core Service API Variability**
   - Services use different calling conventions
   - No clear separation between service and implementation
   - Import paths are complex and nested
   - Dependency injection not consistently applied

4. **Technical Debt from Legacy Code**
   - Legacy code still deeply embedded
   - Hard to distinguish between old and new patterns
   - Migration path unclear for developers

---

## 🎯 Goals

Create a **standardized, consistent architecture** that makes the codebase:

```
Easy to Understand → Easy to Extend → Easy to Maintain
       ↓                   ↓                  ↓
Clear Patterns      Standard APIs      Clean Code
```

### Primary Goals

1. **Unified Configuration System**
   - Single config service with clear precedence
   - Environment variables → TOML files → defaults
   - Pydantic models for validation
   - Easy to understand and modify

2. **Standardized Connector Interface**
   - Protocol-based connector design
   - Consistent API across all connectors
   - Easy to implement new connectors
   - Standard error handling and logging

3. **Clean Core Service API**
   - Simple, consistent service interfaces
   - Clear separation of concerns
   - Easy-to-import public APIs
   - Dependency injection throughout

4. **Refactored Legacy Code**
   - Clear migration path from legacy
   - Minimal breaking changes
   - Backward compatibility where possible
   - Deprecation warnings for old patterns

---

## 👥 Target Users

**Primary: Developers**
- Adding new data sources (connectors)
- Configuring the application
- Understanding the codebase
- Contributing features

**Secondary: End Users**
- Simple configuration via TOML
- Clear error messages
- Predictable behavior

---

## ✅ Acceptance Criteria

### Must Have

#### 1. Configuration System
- [ ] Single `ConfigService` class as entry point
- [ ] Pydantic models for all config types
- [ ] TOML file loading with validation
- [ ] Environment variable override support
- [ ] Default values clearly defined
- [ ] Config merging with clear precedence
- [ ] Documentation of all config options

#### 2. Connector Interface
- [ ] `DocumentConnector` protocol defined
- [ ] Standard methods: `discover()`, `read()`, `metadata()`
- [ ] All connectors implement protocol
- [ ] Connector factory for instantiation
- [ ] Standard error handling across connectors
- [ ] Progress reporting interface

#### 3. Core Services
- [ ] Clean public API in `core.v1.engine.services`
- [ ] Service interfaces clearly defined
- [ ] Factory pattern for service creation
- [ ] Dependency injection via ServiceFactory
- [ ] All services use standard patterns
- [ ] Import paths simplified

#### 4. Legacy Migration
- [ ] Clear deprecation warnings
- [ ] Migration guide document
- [ ] Backward compatibility maintained
- [ ] Tests pass for both old and new APIs

### Nice to Have
- [ ] Performance improvements
- [ ] Enhanced logging
- [ ] Metrics/observability hooks
- [ ] Plugin system for extensions

---

## 🏗️ Technical Architecture

### 1. Configuration Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Configuration Precedence              │
│  Environment Variables → TOML Files → Defaults          │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                     ConfigService                        │
│  ┌───────────────────────────────────────────────────┐  │
│  │  load_config()                                    │  │
│  │  get_indexer_config() → IndexerConfig            │  │
│  │  get_search_config() → SearchConfig              │  │
│  │  get_connector_config(type) → ConnectorConfig    │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                  Pydantic Config Models                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ IndexerConfig│  │ SearchConfig │  │ConnectorConfig│ │
│  │ - embeddings │  │ - max_results│  │ - type        │ │
│  │ - chunk_size │  │ - threshold  │  │ - params      │ │
│  │ - batch_size │  │ - filters    │  │ - credentials │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Config File Structure:**
```toml
# indexed.toml

[indexer]
embedding_model = "all-MiniLM-L6-v2"
chunk_size = 512
chunk_overlap = 50
batch_size = 32

[search]
max_results = 10
similarity_threshold = 0.7
include_metadata = true

[connectors.filesystem]
base_path = "./docs"
include_patterns = ["*.md", "*.txt"]
exclude_patterns = ["node_modules/", ".git/"]

[connectors.confluence]
base_url = "https://company.atlassian.net"
space_keys = ["DEV", "DOCS"]
```

### 2. Connector Architecture

```python
# Standard Protocol
from typing import Protocol, Iterator

class DocumentConnector(Protocol):
    """Standard interface for all document connectors."""
    
    def discover(self) -> Iterator[DocumentMetadata]:
        """Discover available documents."""
        ...
    
    def read(self, doc_id: str) -> Document:
        """Read a specific document."""
        ...
    
    def get_metadata(self, doc_id: str) -> DocumentMetadata:
        """Get metadata for a document."""
        ...

# Usage
connector = ConnectorFactory.create("filesystem", config)
for metadata in connector.discover():
    doc = connector.read(metadata.id)
    # Process document...
```

**Connector Implementations:**
- `FileSystemConnector` - Local files
- `ConfluenceConnector` - Confluence pages
- `JiraConnector` - Jira issues
- Future: `GitConnector`, `NotionConnector`, etc.

### 3. Core Services Architecture

```python
# Clean Public API
from core.v1.engine.services import (
    create,        # Create collection
    update,        # Update collection
    search,        # Search collections
    status,        # Get collection status
    clear,         # Clear collection
    SourceConfig,  # Configuration model
)

# Service Factory (internal)
class ServiceFactory:
    """Create properly configured services."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def create_indexing_service(self) -> IndexingService:
        """Create indexing service with dependencies."""
        embedder = self.create_embedder()
        storage = self.create_storage()
        return IndexingService(embedder, storage, self.config)
    
    def create_search_service(self) -> SearchService:
        """Create search service with dependencies."""
        # ...

# Usage in CLI
config = ConfigService.load()
factory = ServiceFactory(config)
indexing_service = factory.create_indexing_service()
```

### 4. Import Structure Simplification

**Before (Complex):**
```python
from core.v1.engine.core.documents_collection_creator import DocumentCollectionCreator
from core.v1.engine.indexes.indexers.faiss_indexer import FaissIndexer
from core.v1.engine.indexes.embeddings.sentence_embeder import SentenceEmbedder
```

**After (Simple):**
```python
# High-level API (for most users)
from core.v1.engine.services import create, search, status

# Component API (for advanced usage)
from core.v1.engine.indexing import IndexingService
from core.v1.engine.search import SearchService
from core.v1.engine.storage import FAISSStorage
from core.v1.engine.embeddings import SentenceEmbedder
```

---

## 📦 Implementation Plan

### Phase 2.1: Configuration System (Week 1)

**Tasks:**
1. Design Pydantic config models
2. Implement ConfigService with TOML loading
3. Add environment variable support
4. Create default configuration
5. Add config validation
6. Write config documentation

**Deliverables:**
- `core/v1/config/service.py` - ConfigService implementation
- `core/v1/config/models.py` - Pydantic models
- `core/v1/config/defaults.toml` - Default configuration
- `docs/configuration.md` - Configuration guide

### Phase 2.2: Connector Interface (Week 1-2)

**Tasks:**
1. Define DocumentConnector protocol
2. Implement ConnectorFactory
3. Refactor FileSystemConnector to protocol
4. Refactor ConfluenceConnector to protocol
5. Refactor JiraConnector to protocol
6. Add connector tests
7. Document connector API

**Deliverables:**
- `core/v1/connectors/protocol.py` - DocumentConnector protocol
- `core/v1/connectors/factory.py` - ConnectorFactory
- `core/v1/connectors/filesystem.py` - Refactored connector
- `core/v1/connectors/confluence.py` - Refactored connector
- `core/v1/connectors/jira.py` - Refactored connector
- `docs/connectors.md` - Connector development guide

### Phase 2.3: Core Service Refactoring (Week 2)

**Tasks:**
1. Define clean service interfaces
2. Implement ServiceFactory with DI
3. Refactor create/update/search services
4. Simplify import paths
5. Add service documentation
6. Update CLI to use new APIs

**Deliverables:**
- `core/v1/engine/services/__init__.py` - Public API exports
- `core/v1/engine/services/factory.py` - ServiceFactory
- `core/v1/engine/services/*.py` - Refactored services
- Updated CLI commands
- `docs/services.md` - Service API guide

### Phase 2.4: Legacy Migration & Testing (Week 2-3)

**Tasks:**
1. Add deprecation warnings to legacy code
2. Create migration guide
3. Update all tests
4. Performance testing
5. Documentation updates
6. Code cleanup

**Deliverables:**
- `MIGRATION.md` - Migration guide from Phase 1 to Phase 2
- Updated test suite
- Performance benchmarks
- Updated documentation

---

## 🔧 Detailed Technical Specifications

### Configuration Service

```python
# core/v1/config/service.py

from pathlib import Path
from typing import Optional
import toml
from pydantic import ValidationError
from .models import Config, IndexerConfig, SearchConfig

class ConfigService:
    """Unified configuration service."""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self._find_config()
        self._config: Optional[Config] = None
    
    def load(self) -> Config:
        """Load configuration with precedence."""
        # 1. Load defaults
        config_dict = self._load_defaults()
        
        # 2. Merge TOML file
        if self.config_path and self.config_path.exists():
            file_config = toml.load(self.config_path)
            config_dict = self._merge_config(config_dict, file_config)
        
        # 3. Apply environment overrides
        env_config = self._load_from_env()
        config_dict = self._merge_config(config_dict, env_config)
        
        # 4. Validate and return
        try:
            self._config = Config(**config_dict)
            return self._config
        except ValidationError as e:
            raise ConfigError(f"Invalid configuration: {e}")
    
    @staticmethod
    def _find_config() -> Optional[Path]:
        """Find indexed.toml in current directory or parents."""
        current = Path.cwd()
        for parent in [current, *current.parents]:
            config_file = parent / "indexed.toml"
            if config_file.exists():
                return config_file
        return None
```

### Connector Protocol

```python
# core/v1/connectors/protocol.py

from typing import Protocol, Iterator
from dataclasses import dataclass

@dataclass
class DocumentMetadata:
    id: str
    title: str
    url: Optional[str]
    modified_time: datetime
    source_type: str
    extra: dict

class DocumentConnector(Protocol):
    """Standard interface for document connectors."""
    
    def discover(self) -> Iterator[DocumentMetadata]:
        """
        Discover available documents.
        
        Yields:
            DocumentMetadata for each discovered document
        
        Raises:
            ConnectorError: If discovery fails
        """
        ...
    
    def read(self, doc_id: str) -> Document:
        """
        Read full document content.
        
        Args:
            doc_id: Document identifier from metadata
        
        Returns:
            Document with full content
        
        Raises:
            DocumentNotFoundError: If document doesn't exist
            ConnectorError: If read fails
        """
        ...
    
    def get_metadata(self, doc_id: str) -> DocumentMetadata:
        """
        Get document metadata without reading full content.
        
        Args:
            doc_id: Document identifier
        
        Returns:
            DocumentMetadata
        
        Raises:
            DocumentNotFoundError: If document doesn't exist
        """
        ...
    
    def test_connection(self) -> bool:
        """Test if connector can connect to source."""
        ...
```

### Service Factory

```python
# core/v1/engine/services/factory.py

class ServiceFactory:
    """Factory for creating properly configured services."""
    
    def __init__(self, config: Config):
        self.config = config
        self._embedder = None
        self._storage = None
    
    def create_indexing_service(self) -> IndexingService:
        """Create indexing service with dependencies."""
        return IndexingService(
            embedder=self.get_embedder(),
            storage=self.get_storage(),
            config=self.config.indexer
        )
    
    def create_search_service(self) -> SearchService:
        """Create search service with dependencies."""
        return SearchService(
            embedder=self.get_embedder(),
            storage=self.get_storage(),
            config=self.config.search
        )
    
    def get_embedder(self) -> SentenceEmbedder:
        """Get or create embedder (singleton)."""
        if self._embedder is None:
            self._embedder = SentenceEmbedder(
                model_name=self.config.indexer.embedding_model
            )
        return self._embedder
    
    def get_storage(self) -> FAISSStorage:
        """Get or create storage (singleton)."""
        if self._storage is None:
            self._storage = FAISSStorage(
                index_path=self.config.indexer.storage_path
            )
        return self._storage
```

---

## 🧪 Testing Strategy

### Unit Tests
- Config loading with different precedence
- Connector protocol compliance
- Service factory instantiation
- Import path verification

### Integration Tests
- End-to-end indexing workflow
- End-to-end search workflow
- Config changes affecting behavior
- Connector swapping

### Migration Tests
- Legacy API still works
- Deprecation warnings shown
- New API produces same results

---

## 📊 Success Metrics

### Code Quality
- Reduced cyclomatic complexity
- Improved test coverage (>80%)
- Fewer import errors
- Cleaner dependency graph

### Developer Experience
- Faster onboarding (measure time to first PR)
- Fewer questions in code reviews
- Easier to add new connectors
- Clear error messages

### Maintainability
- Less code duplication
- Consistent patterns throughout
- Clear separation of concerns
- Well-documented APIs

---

## 🚫 Out of Scope

- UI enhancements (Phase 3)
- Performance optimization (separate effort)
- New features (focus on refactoring)
- Breaking changes to CLI commands
- Data migration (maintain compatibility)

---

## 📚 Documentation Deliverables

1. **Configuration Guide** (`docs/configuration.md`)
   - All config options explained
   - Examples for common scenarios
   - Environment variable reference

2. **Connector Development Guide** (`docs/connectors.md`)
   - How to implement DocumentConnector
   - Best practices
   - Testing requirements
   - Example implementations

3. **Service API Reference** (`docs/services.md`)
   - Public API documentation
   - Usage examples
   - Architecture diagrams

4. **Migration Guide** (`MIGRATION.md`)
   - Phase 1 → Phase 2 migration
   - Deprecation timeline
   - Code migration examples
   - Breaking changes (if any)

---

## 🔗 Dependencies

### Prerequisites
- ✅ Phase 1 complete (monorepo structure)
- ✅ All CLI commands working
- ✅ MCP server functional

### Blocked By
- None (can start immediately)

### Blocks
- Phase 3: UI enhancements
- Future connector implementations
- Advanced search features

---

## 📅 Timeline

**Week 1: Configuration & Connectors**
- Days 1-3: Configuration system
- Days 4-5: Connector protocol and refactoring

**Week 2: Core Services**
- Days 1-3: Service refactoring
- Days 4-5: CLI integration

**Week 3: Testing & Documentation**
- Days 1-2: Testing and bug fixes
- Days 3-4: Documentation
- Day 5: Code review and cleanup

**Total: 3 weeks**

---

## 🎯 Definition of Done

- [ ] All acceptance criteria met
- [ ] Tests passing (unit + integration)
- [ ] Documentation complete
- [ ] Code review approved
- [ ] Migration guide written
- [ ] No breaking changes to CLI commands
- [ ] Performance maintained or improved
- [ ] Legacy code properly deprecated
- [ ] Memory files updated

---

**End of PRD**
