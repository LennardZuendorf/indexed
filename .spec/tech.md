---
type: entrypoint
scope: tech
children: [cleanup.md, feature-config-tech.md]
updated: 2026-02-16
---

# Tech Spec: indexed

Technical architecture and implementation details for indexed semantic search platform.

**For product decisions (what/why), see [product.md](product.md).**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   User Interfaces                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   CLI App   │  │  MCP Server │  │  Python API │     │
│  │   (Typer)   │  │  (FastMCP)  │  │   (Index)   │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
└─────────┼─────────────────┼─────────────────┼───────────┘
          │                 │                 │
          └─────────────────┴─────────────────┘
                            │
          ┌─────────────────▼─────────────────┐
          │        Service Layer               │
          │  CollectionService                 │
          │  SearchService                     │
          │  InspectService                    │
          │  UpdateService                     │
          │  ClearService                      │
          └─────────────────┬─────────────────┘
                            │
          ┌─────────────────▼─────────────────┐
          │         Engine Layer               │
          │  DocumentCollectionCreator         │
          │  DocumentCollectionSearcher        │
          │  FaissIndexer                      │
          │  SentenceEmbedder                  │
          │  DiskPersister                     │
          └─────────────────┬─────────────────┘
                            │
          ┌─────────────────▼─────────────────┐
          │     Infrastructure Layer           │
          │  Connectors (protocol-based)       │
          │  ConfigService (singleton)         │
          │  Utilities (logging, retry, etc.)  │
          └────────────────────────────────────┘
```

---

## Tech Stack

### Core Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| **Python** | 3.11+ | Language runtime |
| **uv** | 0.5+ | Package manager (workspace support) |
| **FAISS** | latest | Vector similarity search |
| **sentence-transformers** | latest | Embedding generation |
| **Typer** | 0.15.1 | CLI framework |
| **Rich** | 13.0+ | Terminal UI |
| **FastMCP** | latest | MCP server |
| **Pydantic** | 2.10+ | Validation |
| **ruff** | 0.9.1 | Linter + formatter |
| **mypy** | 1.14+ | Type checker |
| **pytest** | 8.3.4 | Testing |

### Monorepo Structure

```
indexed/
├── apps/indexed/              # Main CLI & MCP server
├── packages/
│   ├── indexed-core/         # Indexing & search engine
│   ├── indexed-config/       # Config management
│   ├── indexed-connectors/   # Source connectors
│   └── utils/                # Shared utilities
└── tests/                    # Test suite
```

**Build system:** `una` for bundling workspace into single wheel

---

## Data Flow

### Indexing Pipeline

```
Source API → Reader → Converter → Chunker → Embedder → Indexer → Persister
```

**Detailed:**
1. **Reader** fetches documents from source (Jira API, file system, etc.)
2. **Converter** transforms to standardized `Document` objects
3. **Chunker** splits documents into searchable chunks (512 tokens, 50 overlap)
4. **Embedder** generates vectors (384-dim via `all-MiniLM-L6-v2`)
5. **Indexer** builds FAISS index (`IndexFlatL2` default)
6. **Persister** saves to disk atomically

### Search Pipeline

```
Query → Embedder → FAISS Search → Result Mapper → Formatter
```

**Detailed:**
1. **Embedder** converts query text to vector (same model as indexing)
2. **FAISS Search** finds K nearest neighbors (L2 distance)
3. **Result Mapper** looks up chunks, documents, metadata
4. **Formatter** outputs as card/table/compact/JSON

---

## Storage Architecture

### Directory Structure

```
~/.indexed/                    # Global mode (default)
├── config.toml                # Configuration
├── .env                       # Credentials (not in git)
└── data/
    └── collections/
        └── {collection-name}/
            ├── manifest.json              # Metadata
            ├── documents.json             # Document list
            ├── chunks.json                # Chunk list
            └── index/
                ├── index_info.json
                ├── index_document_mapping.json
                └── indexer_FAISS_*/
                    └── indexer            # Binary FAISS index

./.indexed/                    # Local mode (per-project)
├── config.toml
├── .env
├── .gitignore                 # Auto-created with ".env" entry
└── data/
    └── collections/...
```

**`.gitignore` auto-creation:** When `ensure_storage_dirs(is_local=True)` creates a local `.indexed/` directory, it also creates a `.gitignore` containing `.env`. If `.gitignore` already exists, `.env` is appended if missing. Not applied to `~/.indexed/` (outside git repos).

**CWD/.env:** In addition to `.indexed/.env`, the system also loads `CWD/.env` (standard project-level `.env`) as a credential fallback. See Configuration System below for loading priority.

### Persistence Strategy

**Atomic writes:**
- Write to temp file
- fsync()
- Rename to final location (atomic on POSIX)

**Prevents corruption from:**
- Process crashes
- System crashes
- Disk full errors

---

## Configuration System

### Single-Source Config Resolution

The system resolves to **one** `config.toml` file — local OR global, never both. No merging.

**Mode resolution order** (in `WorkspaceManager.resolve_storage_mode()`):

| Priority | Source | Example |
|----------|--------|---------|
| 1 (highest) | CLI `mode_override` | `--local` / `--global` flag |
| 2 | Workspace preference | Stored in global config `[workspace].mode` |
| 3 | Auto-detect | Local `.indexed/config.toml` exists → local |
| 4 (lowest) | Default | `"global"` |

Once the mode is resolved, `TomlStore.read_for_mode(mode)` reads the single config source. Then env vars (`INDEXED__*`) and CLI arguments are applied on top.

### .env Loading Hierarchy

All `.env` files use `load_dotenv(override=False)` — first loaded wins. Real env vars are never overridden.

| Priority | Source | Description |
|----------|--------|-------------|
| 1 (highest) | Real `os.environ` | Already set before process starts, never touched |
| 2 | `.indexed/.env` | From resolved root (local or global), loaded first |
| 3 (lowest) | `CWD/.env` | Standard project .env, fills gaps only |

`INDEXED__*` env variables are mapped into the TOML config dict separately (not via `.env` loading).

### Implementation

**Key files:**
- `packages/indexed-config/src/indexed_config/service.py` — `ConfigService` slim orchestrator
- `packages/indexed-config/src/indexed_config/store.py` — `TomlStore` with `read_for_mode()`
- `packages/indexed-config/src/indexed_config/workspace.py` — `WorkspaceManager.resolve_storage_mode()`
- `packages/indexed-config/src/indexed_config/env_writer.py` — `EnvFileWriter` (secrets to resolved `.env`)
- `packages/indexed-config/src/indexed_config/registry.py` — `ConfigRegistry` (typed spec registration)

```python
class ConfigService:
    """Singleton config service. Orchestrates registry, store, and workspace."""

    _instance = None

    @classmethod
    def instance(cls) -> "ConfigService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
```

**Validation:** Pydantic models in `packages/indexed-config/src/indexed_config/models.py`

### Config Schema

```toml
[general]
log_level = "INFO"
storage_mode = "global"  # or "local"

[core.v1.indexing]
chunk_size = 512
chunk_overlap = 50
batch_size = 32

[core.v1.embedding]
model_name = "all-MiniLM-L6-v2"

[core.v1.vector_store]
index_type = "IndexFlatL2"

[core.v1.search]
max_docs = 10
max_chunks = 30
include_matched_chunks = true
min_score = 0.0

[mcp]
log_level = "INFO"
json_logs = false
transport = "stdio"
host = "127.0.0.1"
port = 8000
```

---

## Connector Protocol

### Interface

**File:** `packages/indexed-core/src/core/v1/connectors/base.py`

```python
from typing import Protocol, Iterator

class DocumentReader(Protocol):
    def read_documents(self) -> Iterator[RawDocument]:
        """Fetch documents from source."""
        ...

class DocumentConverter(Protocol):
    def convert(self, doc: RawDocument) -> Iterator[Document]:
        """Convert raw document to searchable chunks."""
        ...

class BaseConnector(Protocol):
    @property
    def reader(self) -> DocumentReader: ...

    @property
    def converter(self) -> DocumentConverter: ...

    @property
    def connector_type(self) -> str: ...
```

### Implemented Connectors

| Connector | Location | Protocol | Auth |
|-----------|----------|----------|------|
| **FileSystemConnector** | `packages/indexed-connectors/src/connectors/files/` | Local FS | None |
| **JiraCloudConnector** | `packages/indexed-connectors/src/connectors/jira/` | REST API | Email + Token |
| **JiraServerConnector** | `packages/indexed-connectors/src/connectors/jira/` | REST API | Email + Token |
| **ConfluenceCloudConnector** | `packages/indexed-connectors/src/connectors/confluence/` | REST API | Email + Token |
| **ConfluenceServerConnector** | `packages/indexed-connectors/src/connectors/confluence/` | REST API | Email + Token |

---

## Embedding Strategy

### Model Selection

**Default:** `all-MiniLM-L6-v2`
- 384 dimensions
- ~22MB model size
- Fast inference
- Good quality for general text

**Alternatives:**
- `all-mpnet-base-v2` (768-dim, higher quality, slower)
- `multi-qa-distilbert-cos-v1` (768-dim, optimized for Q&A)

### Lazy Loading

**File:** `packages/indexed-core/src/core/v1/engine/indexes/embeddings/sentence_embedder.py`

```python
def get_embedder():
    """Lazy load to avoid 500ms+ import cost at CLI startup."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)
```

**Result:** CLI startup <0.5s despite heavy ML dependencies

### Batching

**Batch size:** 32 documents (configurable)
**Throughput:** ~120 docs/min on M1 MacBook Pro

---

## FAISS Indexing

### Index Types

| Type | Use Case | Memory | Speed |
|------|----------|--------|-------|
| **IndexFlatL2** | <50K docs (default) | High | Fast |
| IndexIVFFlat | 50K-1M docs | Low | Medium |
| IndexHNSW | >1M docs | Medium | Fast |

**Current:** Only `IndexFlatL2` implemented (exact similarity search)

### Index Creation

**File:** `packages/indexed-core/src/core/v1/engine/indexes/faiss_indexer.py`

```python
import faiss
import numpy as np

# Create index
dimension = 384  # for all-MiniLM-L6-v2
index = faiss.IndexFlatL2(dimension)

# Add vectors
embeddings = np.array(embedding_list).astype('float32')
index.add(embeddings)

# Search
query_embedding = np.array([query_vector]).astype('float32')
distances, indices = index.search(query_embedding, k=10)
```

### Similarity Scoring

**FAISS returns:** L2 distances (lower = more similar)

**Conversion to similarity score (0-1):**
```python
score = 1 / (1 + distance)
```

---

## MCP Server Implementation

### Tools

**File:** `apps/indexed/src/indexed/mcp/server.py`

```python
from fastmcp import FastMCP

mcp = FastMCP("indexed")

@mcp.tool()
def search(query: str, collection: str | None = None) -> dict:
    """Search indexed collections."""
    results = index.search(query, collection)
    return {
        "query": query,
        "results": [
            {
                "text": chunk.text,
                "score": chunk.score,
                "source": chunk.source,
                "collection": chunk.collection,
            }
            for chunk in results
        ],
    }

@mcp.tool()
def list_collections() -> dict:
    """List all collections."""
    collections = index.list_collections()
    return {"collections": [c.name for c in collections]}

@mcp.tool()
def collection_status(name: str) -> dict:
    """Get collection status."""
    status = index.get_status(name)
    return {
        "name": status.name,
        "document_count": status.document_count,
        "chunk_count": status.chunk_count,
        "embedding_model": status.embedding_model,
    }
```

### Resources

```python
@mcp.resource("resource://collections")
def collections_resource() -> str:
    """List of collection names."""
    collections = index.list_collections()
    return "\n".join(c.name for c in collections)

@mcp.resource("resource://collections/status")
def all_collections_status() -> str:
    """Status for all collections."""
    statuses = index.status()
    return json.dumps([s.dict() for s in statuses], indent=2)

@mcp.resource("resource://collections/{name}")
def collection_resource(name: str) -> str:
    """Status for specific collection."""
    status = index.get_status(name)
    return json.dumps(status.dict(), indent=2)
```

### Transports

| Transport | Use Case | Implementation |
|-----------|----------|----------------|
| **stdio** | Claude Desktop, Cline | Default, stdin/stdout |
| **http** | Network access | HTTP server on port 8000 |
| **sse** | Server-Sent Events | SSE streaming |

**File:** `apps/indexed/src/indexed/mcp/cli.py` handles transport selection

---

## Performance Optimizations

### CLI Startup Time

**Target:** <1s
**Actual:** ~500ms

**Techniques:**
1. **Lazy imports** - Heavy ML libraries imported only in commands
2. **Deferred initialization** - Services created on first use
3. **Minimal module-level imports** - Use `TYPE_CHECKING` for type hints
4. **`__getattr__` pattern** - Module-level lazy loading

**Example:**

```python
# commands/search.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.v1 import Index

def search_command(query: str):
    from . import search_command as this_module
    index = this_module.index  # Lazy loaded
    return index.search(query)

def __getattr__(name: str):
    if name == "index":
        from core.v1 import Index
        return Index()
    raise AttributeError(f"module has no attribute '{name}'")
```

### Search Latency

**Target:** <1s for 10K-100K docs
**Actual:** ~800ms (10K), ~1.5s (100K)

**Optimizations:**
1. **Searcher caching** - Reuse loaded FAISS indexes across queries
2. **Memory-mapped indexes** - FAISS loads from disk without full read
3. **Batch embedding** - Process multiple queries efficiently

### Memory Usage

**Idle:** ~80MB
**Indexing:** ~400MB (embedding model + batch data)
**Search:** ~250MB (embedding model + index)

---

## Testing Strategy

### Coverage Requirements

**Target:** >85% coverage
**Measured on:** Installed packages (not source paths)

**Packages:**
- `indexed` (CLI & MCP)
- `core` (engine)
- `connectors` (all connectors)
- `indexed_config` (config system)
- `utils` (utilities)

### Test Organization

```
tests/
├── unit/                      # Package-specific unit tests
│   ├── indexed/              # CLI tests
│   ├── indexed_core/         # Engine tests
│   ├── indexed_connectors/   # Connector tests
│   └── indexed_config/       # Config tests
├── system/                    # Integration tests
└── benchmarks/                # Performance tests
```

### Running Tests

```bash
# All tests
uv run pytest -q

# Specific package
uv run pytest tests/unit/indexed_core/ -q

# With coverage
uv run pytest -q --cov=src --cov-report=html
```

---

## Code Quality

### Linting & Formatting

**Tool:** ruff (replaces flake8 + black)

```bash
# Lint
uv run ruff check .

# Auto-fix
uv run ruff check . --fix

# Format
uv run ruff format .
```

### Type Checking

**Tool:** mypy (strict mode)

```bash
uv run mypy src/
```

**Config:** `pyproject.toml`
```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
ignore_missing_imports = true
```

### Pre-commit Hooks

```bash
# Install
uv run pre-commit install --hook-type pre-commit --hook-type pre-push

# Run manually
uv run pre-commit run --all-files
```

**Hooks:** ruff, mypy, tests (on push)

---

## Build & Distribution

### Monorepo Bundling

**Tool:** `una` - bundles workspace packages into single wheel

```bash
# Build wheel
uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/indexed

# Produces: dist/indexed-0.1.0-py3-none-any.whl
```

**Result:** Single wheel contains all packages (indexed, core, connectors, config, utils)

### Docker

**File:** `Dockerfile` (multi-stage build)

```dockerfile
FROM python:3.11-slim
COPY dist/*.whl /tmp/
RUN pip install /tmp/*.whl
ENTRYPOINT ["indexed"]
```

**Build:**
```bash
uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/indexed
docker build -t indexed .
```

**Run:**
```bash
# Stdio
docker run -i -v ~/.indexed:/root/.indexed indexed

# HTTP
docker run -p 8000:8000 -v ~/.indexed:/root/.indexed indexed mcp --transport http --host 0.0.0.0
```

---

## Architectural Rules

Hard constraints that apply to all code — v2 core, new connectors, and surviving infrastructure.

### Dependency Direction

```
┌──────────────────────────────────────────────────────┐
│  CLI / MCP (apps/indexed/)                           │  ← UI only, thin commands
│  May import: services, core, config, utils           │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Core Engine (packages/indexed-core/)                │  ← Business logic
│  May import: protocols, config, utils                │
│  MUST NOT import: CLI, MCP, concrete connectors      │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Connectors / Plugins                                │  ← Data source adapters
│  May import: protocols, config, utils                │
│  MUST NOT import: core engine, CLI, MCP              │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Config, Utils, Protocols (infrastructure)           │  ← Shared foundation
│  MUST NOT import: anything above                     │
└──────────────────────────────────────────────────────┘
```

**Rules:**
- Dependencies flow **downward only** — never import from a higher layer
- Core engine receives connectors via **dependency injection**, never imports concrete implementations
- Protocols/interfaces live in the lowest layer that needs them
- If two packages would create a circular dependency, extract the shared interface into a lower package

### File Size Limits

| File type | Max lines | Action when exceeded |
|-----------|-----------|---------------------|
| CLI command file | 150 | Extract business logic to a service module |
| Service module | 300 | Split by responsibility |
| Any module | 400 | Split into submodules or extract helpers |

If a file exceeds its limit, it is a sign that responsibilities are mixed. Split before adding more code.

### Config Registration

Config specs are registered **explicitly** during app initialization, never at import time:

```python
# CORRECT — explicit registration function
# core/v2/config.py
def register_config(config_service: ConfigService) -> None:
    config_service.register(SearchConfig, path="core.v2.search")

# Called by app startup:
config = ConfigService.instance()
register_config(config)
```

```python
# WRONG — import-time side effect
# core/v2/__init__.py
_svc = ConfigService.instance()      # side effect at import
_svc.register(SearchConfig, ...)     # silent if fails
```

### Error Handling

All exceptions follow a hierarchy rooted in `IndexedError`:

```python
IndexedError
├── ConfigurationError
│   └── ConfigValidationError
├── StorageError
│   └── StorageConflictError
├── CLIError
└── MCPError
```

**Rules:**
- All package exceptions MUST inherit from `IndexedError`
- NEVER use bare `except Exception: pass` — always log or re-raise
- CLI layer catches `IndexedError` subtypes → user-friendly message + exit code
- MCP layer catches `IndexedError` subtypes → structured error dict
- Unexpected exceptions propagate with full traceback

### No Dual Code Paths

If a value is accessible via dependency injection (e.g., lifespan state, constructor arg) **and** via a global/singleton, pick one path. Never maintain both with fallback logic. Dual paths create subtle bugs where the fallback silently returns stale or default values.

### No Import-Time Side Effects

Module-level code must not:
- Call `ConfigService.instance()` or any singleton accessor
- Register config specs
- Set up logging
- Mutate global state

All initialization happens in explicit `setup_*()` or `register_*()` functions called by the app entry point.

### Thin Commands, Fat Services

CLI commands parse arguments and format output. Business logic lives in service modules:

```
Command (parse args) → Service (orchestrate) → Engine (execute)
       ↓                                              ↓
  Format output                                Return typed result
```

A command file that contains `if/else` branching on business rules is a sign that logic needs extraction.

---

## Open Technical Questions

1. **Index sharding** — How to handle >10M documents? Shard by source? Date range? Needs benchmarking.

2. **Embedding versioning** — If we update the model, how do we handle migration? Store model version in manifest? Automatic re-index?

3. **Concurrent writes** — Currently no locking on collection updates. Add file locking? Atomic swap pattern?

4. **Query caching** — Should we cache query embeddings? Deduplicate identical queries? Cache invalidation strategy?

5. **Connector reliability** — How to handle transient API failures? Retry with exponential backoff? Circuit breaker pattern?

6. **Multi-user server mode** — Database for persistence instead of JSON files? PostgreSQL + pgvector? SQLite?
