# Core Library (`indexed-core`)

## Overview

The Core library provides the essential document indexing, storage, and search functionality. It's designed to be used by the CLI initially, and later extended for server applications. The API is simple but extensible.

## Requirements

### Functional Requirements

**MVP Requirements (Phase 1)**:

**FR-CORE-001: Document Ingestion**
- **MUST** integrate with LlamaIndex for document processing
- **MUST** support basic file formats (PDF, TXT, MD, DOCX) via Unstructured
- **MUST** provide simple text chunking with configurable sizes
- **MUST** extract basic metadata (filename, size, modification time)
- **MUST** handle errors gracefully during ingestion

**FR-CORE-002: Vector Storage**  
- **MUST** implement FAISS vector store for local storage
- **MUST** persist vectors and metadata to local files
- **MUST** support basic collection management (create, delete, list)

**FR-CORE-003: Search Engine**
- **MUST** provide semantic search using embedding vectors
- **MUST** return results with relevance scores
- **MUST** support basic filtering by collection

**FR-CORE-004: Configuration**
- **MUST** support TOML configuration files
- **MUST** provide sensible defaults for all settings
- **MUST** support OpenAI and local embedding providers

**Future Extensions (Phase 2+)**:
- Advanced connectors (Jira, Confluence, etc.)
- Multiple FAISS index types and optimization
- Search result caching and advanced filtering
- Incremental updates and change detection

### Non-Functional Requirements

**NFR-CORE-001: Performance**
- **MUST** process 1000+ documents/hour on standard hardware
- **MUST** support collections up to 100K documents efficiently
- **MUST** return search results within 2 seconds for typical queries
- **MUST** use memory-efficient data structures and algorithms

**NFR-CORE-002: Reliability**
- **MUST** handle errors gracefully without data corruption
- **MUST** provide atomic operations for critical data updates
- **MUST** support crash recovery and data consistency checks
- **MUST** log all operations for debugging and audit purposes

**NFR-CORE-003: Extensibility**
- **MUST** provide clean interfaces for adding new data sources
- **MUST** support pluggable embedding models
- **MUST** allow custom document processors and extractors
- **MUST** provide hooks for monitoring and metrics collection

## Structure

### Library Layout

```
packages/core/
├── __init__.py              # Public API exports
├── config.py                # Configuration management
├── search_engine.py         # Main search engine class
├── collection.py            # Collection management
├── storage/
│   ├── __init__.py
│   ├── vector_store.py      # FAISS vector storage
│   └── document_store.py    # Document metadata storage
├── ingestion/
│   ├── __init__.py
│   ├── pipeline.py          # Document ingestion pipeline
│   └── processors.py       # Document processors
└── utils/
    ├── __init__.py
    ├── file_utils.py        # File handling utilities
    └── logging.py           # Logging configuration
├── __init__.py                  # Public API exports
├── ingestion/                   # Document processing
├── storage/                     # Vector and metadata storage
├── search/                      # Search orchestration  
├── connectors/                  # Data source integrations
├── config/                      # Configuration management
└── utils/                       # Shared utilities
```

### Core API Implementation

**Main SearchEngine Class** (LlamaIndex Native Approach):
```python
from pathlib import Path
from typing import List, Optional, Dict, Any
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.vector_stores.faiss import FaissVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import faiss

class SearchEngine:
    def __init__(self, config: CoreConfig):
        self.config = config
        self.data_dir = Path(config.data_dir)
        self.collections_dir = self.data_dir / "collections"
        self.sources_dir = self.data_dir / "sources"
        
        # PRIMARY: Local HuggingFace embeddings (no API key needed)
        self.embed_model = HuggingFaceEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        # Ensure directories exist
        self.collections_dir.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        
    def create_source(self, source_name: str, documents_path: Path) -> None:
        """Create a new source (becomes a sub-collection)."""
        collection_dir = self.collections_dir / source_name
        collection_dir.mkdir(parents=True, exist_ok=True)
        
        # Load documents using LlamaIndex reader
        reader = SimpleDirectoryReader(str(documents_path))
        documents = reader.load_data()
        
        # Create FAISS vector store with native LlamaIndex approach
        faiss_index = faiss.IndexFlatL2(384)  # all-MiniLM-L6-v2 dimension
        vector_store = FaissVectorStore(faiss_index=faiss_index)
        
        # Create storage context for persistence
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        # Build index with documents
        index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            embed_model=self.embed_model
        )
        
        # Persist using LlamaIndex native persistence
        index.storage_context.persist(persist_dir=str(collection_dir))
        
        # Save source metadata
        source_metadata = {
            "name": source_name,
            "documents_path": str(documents_path),
            "document_count": len(documents),
            "created_at": str(datetime.now())
        }
        
        with open(self.sources_dir / f"{source_name}.json", "w") as f:
            json.dump(source_metadata, f, indent=2)
        
    def search(self, query: str, sources: Optional[List[str]] = None, 
               max_results: int = 10) -> List[Dict[str, Any]]:
        """Search across sources (sub-collections)."""
        if sources is None:
            sources = self.list_sources()
            
        all_results = []
        for source_name in sources:
            source_results = self._search_source(source_name, query, max_results)
            all_results.extend(source_results)
            
        # Sort by relevance and limit
        all_results.sort(key=lambda x: x['score'], reverse=True)
        return all_results[:max_results]
        
    def list_sources(self) -> List[str]:
        """List all available sources."""
        if not self.collections_dir.exists():
            return []
        return [d.name for d in self.collections_dir.iterdir() if d.is_dir()]
        
    def _search_source(self, source_name: str, query: str, 
                      limit: int) -> List[Dict[str, Any]]:
        """Search within a specific source."""
        collection_dir = self.collections_dir / source_name
        if not collection_dir.exists():
            return []
            
        # Load persisted index using LlamaIndex native loading
        storage_context = StorageContext.from_defaults(
            persist_dir=str(collection_dir)
        )
        
        index = VectorStoreIndex.from_storage_context(
            storage_context, 
            embed_model=self.embed_model
        )
        
        # Query using retriever for more control
        retriever = index.as_retriever(similarity_top_k=limit)
        nodes = retriever.retrieve(query)
        
        # Format results
        results = []
        for node in nodes:
            results.append({
                'text': node.node.text,
                'score': node.score,
                'metadata': node.node.metadata,
                'source': source_name
            })
            
        return results
```

**Public API Exports** (`__init__.py`):
```python
from .config import CoreConfig
from .search_engine import SearchEngine
from .collection import Collection

__all__ = [
    "CoreConfig",
    "SearchEngine", 
    "Collection",
]

# Simple usage functions
def create_search_engine(data_dir: Optional[Path] = None) -> SearchEngine:
    """Create a search engine with default configuration."""
    config = CoreConfig(data_dir=data_dir or Path.home() / ".llamaindex-search")
    return SearchEngine(config)
```

## Jobs to be Done

### Job 1: Document Ingestion
**When** a developer wants to index documents from various sources  
**I want** to easily configure and run an ingestion pipeline  
**So that** documents are processed, chunked, and stored efficiently

**Acceptance Criteria**:
- Support for 20+ document formats via Unstructured
- Configurable chunking with size and overlap parameters
- Automatic metadata extraction (title, timestamps, structure)
- Progress tracking with detailed status reporting
- Error handling with retry logic and detailed error messages

### Job 2: Vector Search
**When** a user performs a semantic search query  
**I want** to get relevant results quickly with good ranking  
**So that** they can find the information they need efficiently

**Acceptance Criteria**:
- Sub-2-second response times for typical queries
- Relevance ranking based on semantic similarity and metadata
- Support for metadata filtering (source, date, type, etc.)
- Result aggregation across multiple collections
- Caching for improved performance on repeated queries

### Job 3: Collection Management
**When** managing document collections over time  
**I want** to add, update, and maintain collections easily  
**So that** the search index stays current and accurate

**Acceptance Criteria**:
- Incremental updates based on modification timestamps
- Backup and restore functionality
- Collection statistics and health monitoring
- Data migration tools for schema changes
- Cleanup tools for removing outdated documents

### Job 4: Data Source Integration
**When** connecting to external data sources  
**I want** reliable, authenticated access with proper error handling  
**So that** documents can be ingested from various enterprise systems

**Acceptance Criteria**:
- Support for Jira Cloud/Server with JQL filtering
- Support for Confluence Cloud/Server with CQL filtering
- Robust authentication handling (tokens, OAuth, basic auth)
- Rate limiting and retry logic for API calls
- Detailed logging for troubleshooting connection issues

## Technical Implementation

### Ingestion Pipeline Architecture

```python
class IngestionPipeline:
    """LlamaIndex IngestionPipeline wrapper with additional functionality."""
    
    def __init__(
        self,
        transformations: List[Transformation],
        vector_store: VectorStore,
        docstore: Optional[Docstore] = None,
        cache: Optional[IngestionCache] = None,
    ):
        self.pipeline = IngestionPipeline(
            transformations=transformations,
            vector_store=vector_store,
            docstore=docstore,
            cache=cache,
        )
    
    async def run_async(
        self,
        documents: List[Document],
        show_progress: bool = True,
        num_workers: int = 4,
    ) -> List[BaseNode]:
        """Run ingestion pipeline asynchronously with progress tracking."""
        # Implementation with progress bars, error handling, etc.
```

### Vector Storage Design

```python
class FaissVectorStore:
    """Enhanced FAISS vector store with adaptive indexing."""
    
    def __init__(
        self,
        dimension: int,
        index_type: str = "auto",
        persist_path: Optional[str] = None,
    ):
        self.dimension = dimension
        self.persist_path = persist_path
        self.index = self._create_index(index_type)
    
    def _create_index(self, index_type: str) -> faiss.Index:
        """Create appropriate FAISS index based on type and collection size."""
        if index_type == "auto":
            # Auto-select based on expected collection size
            return self._auto_select_index()
        # Implementation for specific index types
    
    def adaptive_search(
        self,
        query_embedding: List[float],
        k: int = 10,
        filters: Optional[Dict] = None,
    ) -> VectorStoreQueryResult:
        """Search with automatic performance optimization."""
        # Implementation with caching, filtering, ranking
```

### Search Engine Design

```python
class SearchEngine:
    """Main search orchestration engine."""
    
    def __init__(self, config: CoreConfig):
        self.config = config
        self.collections = {}
        self.cache = SearchCache()
    
    async def search(
        self,
        query: str,
        collections: Optional[List[str]] = None,
        filters: Optional[Dict] = None,
        max_results: int = 10,
    ) -> SearchResults:
        """Perform semantic search across collections."""
        
        # 1. Process and embed query
        query_embedding = await self._embed_query(query)
        
        # 2. Search relevant collections
        if collections is None:
            collections = list(self.collections.keys())
        
        # 3. Parallel search across collections
        collection_results = await asyncio.gather(*[
            self._search_collection(col, query_embedding, filters, max_results)
            for col in collections
        ])
        
        # 4. Aggregate and rank results
        return self._aggregate_results(collection_results, max_results)
```

### Connector Architecture

```python
class BaseConnector(ABC):
    """Base interface for data source connectors."""
    
    @abstractmethod
    async def read_documents(
        self,
        start_time: Optional[datetime] = None,
    ) -> AsyncIterator[Document]:
        """Read documents from the data source."""
    
    @abstractmethod
    def get_connector_info(self) -> Dict[str, Any]:
        """Get connector metadata and configuration."""

class JiraConnector(BaseConnector):
    """Jira Cloud/Server connector implementation."""
    
    def __init__(
        self,
        base_url: str,
        credentials: JiraCredentials,
        jql: str,
        batch_size: int = 100,
    ):
        self.client = self._create_client(base_url, credentials)
        self.jql = jql
        self.batch_size = batch_size
    
    async def read_documents(
        self,
        start_time: Optional[datetime] = None,
    ) -> AsyncIterator[Document]:
        """Read Jira issues as documents."""
        # Implementation with pagination, rate limiting, error handling
```

## Integration Points

### LlamaIndex Integration

The core component provides a clean wrapper around LlamaIndex components while adding additional functionality:

- **IngestionPipeline**: Enhanced with progress tracking, error handling, and async support
- **VectorStoreIndex**: Extended with adaptive indexing and performance optimizations
- **SimpleDirectoryReader**: Integrated with Unstructured for better format support
- **Embeddings**: Support for multiple embedding providers with fallback options

### FAISS Integration

Direct integration with FAISS for high-performance vector search:

- **Multiple Index Types**: Automatic selection based on collection characteristics
- **Memory Optimization**: Efficient memory usage for large collections
- **Persistence**: Reliable serialization and deserialization
- **Concurrent Access**: Thread-safe operations for multi-user scenarios

### Unstructured Integration

Seamless integration with Unstructured for document parsing:

- **Format Support**: 20+ document formats supported out of the box
- **Metadata Extraction**: Automatic extraction of document structure and metadata
- **Error Handling**: Graceful handling of unsupported or corrupted files
- **Performance**: Optimized parsing with caching and batch processing

## Testing Strategy

### Unit Tests
- Individual component functionality
- Configuration validation
- Error handling scenarios
- Performance benchmarks

### Integration Tests
- End-to-end ingestion pipeline
- Search functionality across different data sources
- Multi-collection operations
- Persistence and recovery

### Performance Tests
- Large document collection handling
- Concurrent search requests
- Memory usage optimization
- Index build and update times

## Dependencies & Packaging

### pyproject.toml for packages/core
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "indexed-core"
version = "0.1.0"
description = "Core search engine for LlamaIndex Search CLI"
readme = "README.md"
requires-python = ">=3.10"
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

dependencies = [
    # Core LlamaIndex (simplified stack)
    "llama-index-core>=0.11.0,<0.12.0",
    "llama-index-embeddings-huggingface>=0.3.0,<0.4.0",  # PRIMARY
    "llama-index-vector-stores-faiss>=0.2.0,<0.3.0",
    "llama-index-readers-file>=0.2.0,<0.3.0",
    
    # Vector storage
    "faiss-cpu>=1.7.4,<2.0.0",
    
    # Document processing
    "unstructured[pdf,docx,md]>=0.15.0,<0.16.0",
    
    # Configuration
    "pydantic>=2.5.0,<3.0.0",
    "pydantic-settings>=2.1.0,<3.0.0",
    "tomli-w>=1.0.0,<2.0.0",
]

[project.optional-dependencies]
gpu = ["faiss-gpu>=1.7.4,<2.0.0"]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "mypy>=1.5.0",
    "ruff>=0.1.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.hatch.build.targets.sdist]
include = [
    "/src",
    "/tests",
    "/README.md",
]
```

### Directory Structure for Packaging
```
packages/core/
├── pyproject.toml
├── README.md
├── src/
│   └── llamaindex_search_core/
│       ├── __init__.py
│       ├── config.py
│       ├── search_engine.py
│       └── ...
└── tests/
    └── test_search_engine.py
```

This core component provides a solid foundation that other packages can build upon while maintaining clean interfaces and high performance.