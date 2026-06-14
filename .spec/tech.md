---
type: entrypoint
scope: tech
children: [tech-app.md, tech-core.md, tech-config.md, tech-connectors.md, tech-parsing.md]
updated: 2026-06-11
---

# Tech Spec: indexed

High-level architecture summary. Cross-cutting concerns + per-component pointers.
Component internals live in the branch docs below.

**For product decisions (what/why), see [product.md](product.md).**

---

## Component Specs

One tech branch doc per monorepo component:

| Component | Branch doc | Covers |
|-----------|-----------|--------|
| `apps/indexed` | [tech-app.md](tech-app.md) | CLI architecture, storage-mode, Rich UI, logging, MCP server |
| `packages/indexed-core` | [tech-core.md](tech-core.md) | engine, embedding, FAISS, persistence, search perf |
| `packages/indexed-config` | [tech-config.md](tech-config.md) | config resolution, .env hierarchy, storage layout, schema versioning |
| `packages/indexed-connectors` | [tech-connectors.md](tech-connectors.md) | connector protocol, implemented connectors, change tracking |
| `packages/indexed-parsing` | [tech-parsing.md](tech-parsing.md) | ParsingModule, Docling, tree-sitter |

`packages/utils` (logging, retry, batching) is a thin shared foundation — no separate
doc; helpers are imported by every layer.

---

## Architecture Overview

```text
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

Layer detail: app → [tech-app.md](tech-app.md); engine → [tech-core.md](tech-core.md);
connectors → [tech-connectors.md](tech-connectors.md); config → [tech-config.md](tech-config.md).

---

## Tech Stack

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
| **Docling / tree-sitter** | latest | Document & code parsing |
| **ruff** | 0.9.1 | Linter + formatter |
| **mypy** | 1.14+ | Type checker |
| **pytest** | 8.3.4 | Testing |

### Monorepo Structure

```text
indexed/
├── apps/indexed/              # Main CLI & MCP server
├── packages/
│   ├── indexed-core/         # Indexing & search engine
│   ├── indexed-config/       # Config management
│   ├── indexed-connectors/   # Source connectors
│   ├── indexed-parsing/      # Shared parsing module (Docling, tree-sitter)
│   └── utils/                # Shared utilities (logging, retry, batching)
└── tests/                    # Test suite
```

**Build system:** `una` bundles the workspace into a single wheel.

---

## Data Flow

Cross-component pipelines. Component internals: [tech-core.md](tech-core.md),
[tech-connectors.md](tech-connectors.md), [tech-parsing.md](tech-parsing.md).

### Indexing Pipeline

```text
Source API → Reader → Converter → Chunker → Embedder → Indexer → Persister
```

1. **Reader** fetches documents from source (Jira API, file system, etc.)
2. **Converter** transforms to standardized `Document` objects
3. **Chunker** splits into searchable chunks (512 tokens, 50 overlap)
4. **Embedder** generates vectors (384-dim via `all-MiniLM-L6-v2`)
5. **Indexer** builds FAISS index (`IndexFlatL2` default)
6. **Persister** saves to disk atomically

### Search Pipeline

```text
Query → Embedder → FAISS Search → Result Mapper → Formatter
```

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
engine = "v2"            # "v2" (LlamaIndex, default) or "v1" (legacy FAISS)

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

# v2 (LlamaIndex) engine config — registered explicitly at app startup via
# core.v2.config.register_config(); see "Engine Selection" below.
[core.v2.embedding]
model_name = "all-MiniLM-L6-v2"

[core.v2.indexing]
chunk_size = 512        # None/unset keeps connector chunking (no re-split)

[core.v2.storage]
vector_store = "faiss"

[core.v2.search]
max_docs = 10
max_chunks = 30
include_matched_chunks = true
score_threshold = null

[mcp]
log_level = "INFO"
json_logs = false
transport = "stdio"
host = "127.0.0.1"
port = 8000
```

### Engine Selection (v1 / v2)

The core engine is selectable. **v2 (LlamaIndex-powered) is the default**; v1 is
the legacy custom-FAISS engine kept for backward compatibility.

**Resolution precedence** (highest first), in `indexed.services.engine_router.get_effective_engine`:

| Priority | Source |
|----------|--------|
| 1 | Per-command `--engine v1\|v2` flag |
| 2 | Root `--engine` flag (stored on `ctx.obj["engine"]`) |
| 3 | On-disk `manifest.json` auto-detection for a *named* collection (v2 manifests carry `"version": "2.x"`) |
| 4 | `[general] engine` in config.toml |
| 5 | Built-in default: `"v2"` |

Manifest auto-detection (3) means **existing v1 collections keep working under the
v2 default** — a per-collection operation detects v1 from its manifest. New
collections default to v2. v2 storage is **not** backward-compatible with v1;
re-index to migrate. `indexed info engine` reports the active engine and how to switch.

- **Router:** `apps/indexed/src/indexed/services/engine_router.py` (resolution) +
  `engine_dispatch.py` (engine→service module). MCP routes through these getters;
  CLI commands resolve via `get_effective_engine` then dispatch per engine.
- **v2 config registration is explicit** at app startup (`_ensure_configs_registered`
  in `app.py`), never at import time.

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

**Target:** >85% coverage, measured on installed packages (`indexed`, `core`,
`connectors`, `indexed_config`, `utils`).

```text
tests/
├── unit/          # package-specific (indexed, indexed_core, indexed_connectors, indexed_config)
├── system/        # integration tests
└── benchmarks/    # performance tests
```

```bash
uv run pytest -q                          # all
uv run pytest tests/unit/indexed_core/ -q # one package
uv run pytest -q --cov=src --cov-report=html
```

---

## Build & Distribution

### Monorepo bundling

`una` bundles all workspace packages into a single wheel.

```bash
# Build wheel (HATCH_BUILD_HOOKS_ENABLE=1 required to bundle workspace packages)
HATCH_BUILD_HOOKS_ENABLE=1 uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/indexed
# → dist/indexed-0.1.0-py3-none-any.whl  (indexed + core + connectors + parsing + config + utils)
```

### Docker

```dockerfile
FROM python:3.11-slim
COPY dist/*.whl /tmp/
RUN pip install /tmp/*.whl
ENTRYPOINT ["indexed"]
```

```bash
docker build -t indexed .
docker run -i -v ~/.indexed:/root/.indexed indexed                                  # stdio
docker run -p 8000:8000 -v ~/.indexed:/root/.indexed indexed mcp --transport http --host 0.0.0.0
```

---

## Architectural Rules

Hard constraints across all code — v2 core, new connectors, surviving infrastructure.

### Dependency Direction

```text
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
│  May import: protocols, config, utils, parsing       │
│  MUST NOT import: core engine, CLI, MCP              │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Config, Utils, Parsing, Protocols (infrastructure)  │  ← Shared foundation
│  MUST NOT import: anything above                     │
└──────────────────────────────────────────────────────┘
```

- Dependencies flow **downward only** — never import from a higher layer
- Core engine receives connectors via **dependency injection**, never imports concrete implementations
- Protocols/interfaces live in the lowest layer that needs them
- Circular dependency → extract the shared interface into a lower package

### File Size Limits

| File type | Max lines | Action when exceeded |
|-----------|-----------|---------------------|
| CLI command file | 150 | Extract business logic to a service module |
| Service module | 300 | Split by responsibility |
| Any module | 400 | Split into submodules or extract helpers |

### Config Registration

Config specs are registered **explicitly** during app initialization, never at import time:

```python
# CORRECT — explicit registration function
def register_config(config_service: ConfigService) -> None:
    config_service.register(SearchConfig, path="core.v2.search")

# WRONG — import-time side effect in __init__.py
_svc = ConfigService.instance()      # side effect at import
_svc.register(SearchConfig, ...)     # silent if fails
```

### Error Handling

All exceptions inherit from `IndexedError`:

```text
IndexedError
├── ConfigurationError
│   └── ConfigValidationError
├── StorageError
│   └── StorageConflictError
├── CLIError
└── MCPError
```

- All package exceptions MUST inherit from `IndexedError`
- NEVER use bare `except Exception: pass` — always log or re-raise
- CLI layer catches `IndexedError` subtypes → user-friendly message + exit code
- MCP layer catches `IndexedError` subtypes → structured error dict
- Unexpected exceptions propagate with full traceback

### No Dual Code Paths

If a value is accessible via dependency injection (lifespan state, constructor arg)
**and** via a global/singleton, pick one path. Never maintain both with fallback logic.

### No Import-Time Side Effects

Module-level code must not call singleton accessors, register config specs, set up
logging, or mutate global state. All initialization happens in explicit
`setup_*()` / `register_*()` functions called by the app entry point.

### Thin Commands, Fat Services

```text
Command (parse args + format output) → Service (orchestrate) → Engine (execute)
```

A command file branching on business rules is a sign logic needs extraction.

---

## Open Technical Questions

1. **Index sharding** — handle >10M documents? Shard by source? Date range? Needs benchmarking.
2. **Embedding versioning** — model update migration? Store model version in manifest? Auto re-index?
3. **Concurrent writes** — no locking on collection updates today. File locking? Atomic swap?
4. **Query caching** — cache query embeddings? Deduplicate identical queries? Invalidation?
5. **Connector reliability** — transient API failures: retry with backoff? Circuit breaker?
6. **Multi-user server mode** — DB instead of JSON files? PostgreSQL + pgvector? SQLite?
