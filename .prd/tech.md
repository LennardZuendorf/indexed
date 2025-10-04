# Technology Stack - Migration to LlamaIndex

## Implementation Goal
Implement the existing `indexed` CLI system using LlamaIndex + FAISS + HuggingFace embeddings instead of custom implementations. Preserve existing command structure and functionality.

## Core Technologies (LlamaIndex Migration)

### 🧠 RAG Framework: LlamaIndex
**Primary Framework**: `llama-index-core` (v0.11.0+)

**Why LlamaIndex**:
- **Purpose-built**: Designed specifically for document indexing and retrieval
- **Native Storage**: Built-in persistence and collection management
- **Simple Integration**: Easy to set up vector stores and embeddings
- **Community**: Active development with good documentation

**Core Dependencies (Simplified Stack)**:
```toml
# Core LlamaIndex packages
llama-index-core = "^0.11.0"
llama-index-embeddings-huggingface = "^0.3.0"  # PRIMARY: Local embeddings
llama-index-vector-stores-faiss = "^0.2.0"     # Vector storage
llama-index-readers-file = "^0.2.0"            # Document loading

# CLI Framework
typer = {version = "^0.12.0", extras = ["all"]}
rich = "^13.7.0"

# MCP Integration
fastmcp = "^2.11.0"

# Vector storage (native FAISS)
faiss-cpu = "^1.7.4"

# Document processing  
unstructured = {version = "^0.15.0", extras = ["pdf", "docx", "md"]}
```

**Implementation Pattern** (Using LlamaIndex components):
```python
# Use LlamaIndex components for clean implementation

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.vector_stores.faiss import FaissVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import faiss

# Clean SearchEngine implementation with LlamaIndex
class SearchEngine:
    def __init__(self, config):
        # PRIMARY: Local HuggingFace embeddings (no API keys)
        self.embed_model = HuggingFaceEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        # Use LlamaIndex FAISS integration
        faiss_index = faiss.IndexFlatL2(384)  # all-MiniLM-L6-v2 dimension
        self.vector_store = FaissVectorStore(faiss_index=faiss_index)
        
        # LlamaIndex handles the indexing pipeline
        storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
        self.index = VectorStoreIndex.from_documents(
            documents, storage_context=storage_context, embed_model=self.embed_model
        )
```

### 🔍 Vector Search: FAISS
**Library**: `faiss-cpu` (v1.7.0+)

**Why FAISS**:
- **Local-first**: No external dependencies or API calls
- **Fast**: Optimized similarity search
- **Simple**: Works well with LlamaIndex integration

**Implementation Strategy**:
- Use LlamaIndex's `FaissVectorStore` with `IndexFlatL2` for simplicity and accuracy
- Use LlamaIndex `HuggingFaceEmbedding` provider instead of direct SentenceTransformers
- Fresh implementation - no migration concerns

### 📄 Document Processing: Unstructured
**Library**: `unstructured[all-docs]` (v0.10.0+)

**Why Unstructured**:
- **Format coverage**: Supports 20+ document formats out of the box
- **Quality extraction**: Advanced parsing for complex documents (tables, metadata)
- **LlamaIndex integration**: Native support via SimpleDirectoryReader
- **Active development**: Regular updates and format additions

**Supported Formats**: PDF, DOCX, PPTX, TXT, HTML, MD, CSV, XLSX, RTF, ODT, ODP, EML, MSG, and more

## Framework Stack

### 🖥️ CLI Framework: Typer + Rich

**Dependencies**:
```toml
typer = {version = "^0.12.0", extras = ["all"]}
rich = "^13.7.0"
```

**CLI Structure**:
```python
import typer
from rich.console import Console
from rich.progress import Progress
from typing_extensions import Annotated

app = typer.Typer(name="indexed")
console = Console()

@app.command()
def index(
    path: Annotated[str, typer.Argument(help="Path to documents")],
    name: Annotated[str, typer.Option("--name", "-n")] = "default",
) -> None:
    """Index documents from a directory."""
    with Progress() as progress:
        # Implementation here
        pass

@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Search query")],
    collection: Annotated[str, typer.Option("--collection", "-c")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 10,
) -> None:
    """Search indexed documents."""
    # Implementation here
    pass
```


### 🤖 MCP Integration: FastMCP
**FastMCP** (v2.11.0+)

**Why FastMCP**:
- **Modern implementation**: Built for performance and developer experience
- **Standards compliant**: Full MCP protocol support
- **Python native**: Seamless integration with our Python stack
- **Extensible**: Easy to add custom tools and resources

## Development Tools

### 📦 Package Management: pip/uv
**Primary**: Standard `pip` for broad compatibility
**Alternative**: `uv` for faster development workflows

**Why start simple**:
- **Compatibility**: pip works everywhere
- **KISS**: Don't add complexity until needed

### 🏗️ Build System: Hatchling
**Hatchling** for packaging

**Why**:
- **Modern**: PEP 517/518 compliant
- **Simple**: Good for monorepo structure

### 🧪 Testing: pytest + Extensions
**pytest** (v7.0.0+)

**Extensions**:
- `pytest-asyncio`: Async test support
- `pytest-cov`: Coverage reporting
- `pytest-mock`: Mocking utilities

**Why pytest**:
- **Industry standard**: Most popular Python testing framework  
- **Flexible**: Fixtures, parametrization, plugins
- **Async support**: Built-in async test capabilities

### 🔧 Code Quality: Ruff + mypy
**Ruff** (v0.1.0+):
- **Speed**: Extremely fast linting and formatting (100x faster than alternatives)
- **Comprehensive**: Combines multiple tools (flake8, isort, black features)
- **Configuration**: Single tool for linting, formatting, import sorting

**mypy** (v1.5.0+):
- **Type safety**: Static type checking for Python
- **Configuration**: Strict mode enabled for high code quality

## Data & Storage

### 🗄️ Vector Storage
**CLI/Local (Current)**: FAISS with local file persistence
- File-based index storage via LlamaIndex
- Memory-mapped for efficiency
- Native LlamaIndex serialization/deserialization
- Zero configuration required

**Server/Cloud (Future - Long-term)**:
- **Supabase pgvector**: PostgreSQL with vector extensions for hosted deployments
- **Qdrant**: Self-hosted vector database for on-premise server deployments
- **Hybrid Architecture**: CLI stays local, server can use cloud options

### 💾 Metadata Storage
**CLI/Local**: SQLite (v3.40.0+)
- Zero configuration
- Embedded, serverless
- Perfect for single-user scenarios

**Server**: PostgreSQL (v15.0+)  
- Multi-user support
- ACID compliance
- JSON support for flexible schemas
- Horizontal scaling capabilities

### 📝 Configuration Management

**Dependencies**:
```toml
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"
tomli-w = "^1.0.0"  # Writing TOML files
```

**Configuration Structure** (Compatible with existing system):
```python
from pydantic import BaseSettings
from pathlib import Path
from typing import Optional, Dict, Any

class IndexedSettings(BaseSettings):
    """Migration-compatible settings matching existing config.toml structure"""
    
    # Sources (existing pattern)
    sources: Dict[str, Dict[str, Any]] = {}
    
    # Search defaults (existing pattern) 
    search: Dict[str, Any] = {
        "max_docs": 10,
        "max_chunks": 30,
        "include_full_text": False
    }
    
    # Paths (existing pattern)
    paths: Dict[str, str] = {
        "collections_dir": "./data/collections",
        "cache_dir": "./data/caches"
    }
    
    # Index settings (migrate to LlamaIndex)
    index: Dict[str, str] = {
        "default_indexer": "llamaindex_openai_ada002",  # NEW: LlamaIndex naming
        "embedding_provider": "openai"
    }
    
    # MCP settings (existing pattern)
    mcp: Dict[str, Any] = {
        "default_sources": [],
        "tool_prefix": "indexed_"
    }
    
    class Config:
        env_prefix = "INDEXED__"  # Existing pattern
        env_file = ".env"
```

**Storage Layout** (LlamaIndex Native Approach):
```
./                           # Project root
├── config.toml              # Configuration (pydantic-settings)
├── .env                     # Environment variables (optional)
└── data/                    # Data directory
    ├── sources/             # Source configurations
    │   └── {source_name}.json   # Source metadata and settings
    └── collections/         # LlamaIndex collections (one per source)
        └── {source_name}/   # Each source becomes a sub-collection
            ├── docstore.json        # LlamaIndex document store
            ├── index_store.json     # LlamaIndex index store
            ├── vector_store.json    # LlamaIndex vector store config
            └── storage/             # FAISS index files
                ├── default__vector_store.faiss
                └── default__vector_store.pkl
```

**Key Change**: Use LlamaIndex's native storage context and persistence, with each source as a separate sub-collection.

## Deployment & Operations

### 🐳 Containerization: Docker
**Base Images**:
- `python:3.11-slim`: Minimal Python runtime
- `python:3.11-alpine`: Ultra-lightweight (where compatible)
- `nvidia/cuda:12.0-runtime-ubuntu20.04`: GPU support

**Docker Compose** (v2.0+):
- Development environments
- Multi-service deployments
- Easy local testing

### ☸️ Orchestration: Kubernetes (Future)
**For production deployments**:
- Auto-scaling based on load
- High availability and fault tolerance
- Rolling deployments
- Resource management

## AI/ML Integration

### 🎯 Embedding Models (Primary: Local HuggingFace)

**Primary: Local Models (HuggingFace via LlamaIndex)**:
- `sentence-transformers/all-MiniLM-L6-v2`: **DEFAULT** - Fast, balanced, local
- `sentence-transformers/all-mpnet-base-v2`: Higher quality option
- `BAAI/bge-small-en-v1.5`: Latest, optimized for retrieval

**Server/Cloud Options (Future - Long-term)**:
- `text-embedding-ada-002`: OpenAI embeddings for server deployments
- `text-embedding-3-small`: Cost-effective OpenAI option
- Cohere embeddings: Alternative cloud provider
- **Hybrid Model**: CLI stays local (HuggingFace), server can use cloud

### 🧠 LLM Integration
**OpenAI API**: GPT-4, GPT-3.5-turbo for query processing, summarization  
**Anthropic Claude**: Alternative LLM provider  
**Local Models** (Future): llama.cpp, Ollama for privacy-focused deployments

## Security & Authentication

### 🔐 Authentication
**JWT Tokens**: `python-jose[cryptography]` for stateless auth
**OAuth 2.0/OIDC**: `authlib` for third-party authentication
**Password Hashing**: `bcrypt` for secure password storage

### 🛡️ Encryption
**At Rest**: `cryptography` library for data encryption
**In Transit**: TLS 1.3 for all network communications
**Key Management**: Environment variables, secret management systems

## Platform Support

### 🖥️ Operating Systems
- **Linux**: Ubuntu 20.04+, RHEL 8+, Debian 11+
- **macOS**: 11.0+ (Big Sur)
- **Windows**: 10+, Windows Server 2019+

### 🏗️ Hardware Architectures  
- **x86_64**: Primary support (Intel/AMD)
- **ARM64**: Apple Silicon, ARM servers
- **GPU**: NVIDIA CUDA support for accelerated search

### 🐍 Python Versions
- **Minimum**: Python 3.10 (for modern type hints, pattern matching)
- **Recommended**: Python 3.11 (best performance)
- **Supported**: Python 3.10, 3.11, 3.12
- **Future**: Python 3.13 when stable

## Development Workflow

### 🔄 Version Control
**Git** with **GitHub**:
- Feature branch workflow
- Pull request reviews
- Automated testing on PRs
- Release tagging and automation

### 🤖 CI/CD: GitHub Actions
**Workflows**:
- **Test**: Run tests on multiple Python versions/OSes
- **Build**: Build all packages on commits
- **Release**: Automated PyPI releases on tags
- **Docker**: Build and push container images

### 📚 Documentation: MkDocs
**MkDocs** with **Material theme**:
- Beautiful, searchable documentation
- Code examples with syntax highlighting
- API documentation generation
- Deployment to GitHub Pages

## Package Distribution

### 📦 Python Packages (PyPI)
**Shared Libraries**:
- `llamaindex-search-core`: Core search engine (shared library)
- `llamaindex-search-mcp-base`: MCP integration base (shared library)

**Applications**:
- `llamaindex-search-cli`: Command-line application
- `llamaindex-search-server`: Web server application

**Distribution**: Wheel + source distributions, signed packages

### 🐳 Container Images (Docker Hub)
**Images**:
- `llamaindex-search:cli`: CLI application container
- `llamaindex-search:server`: Server application container
- `llamaindex-search:both`: Container with both CLI and Server (shared data layer)

## Monitoring & Observability (Future)

### 📊 Metrics: Prometheus + Grafana
- System metrics (CPU, memory, disk)
- Application metrics (search latency, throughput)
- Business metrics (user activity, collection growth)

### 🔍 Logging: Structured JSON logs
- Request/response logging
- Error tracking and alerting
- Performance profiling
- Audit trails for compliance

### 📈 Analytics: Custom dashboard
- User behavior analytics
- Search query analytics
- Performance optimization insights
- A/B testing framework

## Decision Rationale

### Why this stack?

1. **Python Ecosystem**: Rich AI/ML libraries, strong typing, great tooling
2. **LlamaIndex Foundation**: Purpose-built for our use case, active ecosystem
3. **Local-first Architecture**: FAISS + SQLite enable offline operation
4. **Modern Frameworks**: FastAPI, Next.js, Typer provide excellent DX
5. **Container Native**: Docker/K8s for modern deployment patterns
6. **Developer Experience**: Fast tools (UV, Ruff), great debugging, clear errors
7. **Scalability**: Architecture supports local → team → enterprise progression
8. **Community**: All major components have strong communities and documentation

### Trade-offs Made

1. **Python-only backend**: Simpler development vs potential performance gains from Go/Rust
2. **FAISS over vector DBs**: Local-first vs cloud-native scalability
3. **Monorepo structure**: Unified development vs independent package evolution
4. **SQLite for local**: Simplicity vs advanced features of PostgreSQL everywhere
5. **FastAPI over Django**: API-focused vs full-framework batteries-included

This technology stack provides a solid foundation for building a modern, scalable, and maintainable document search platform while prioritizing developer experience and deployment flexibility.