---
type: entrypoint
scope: tech
children: [tech-app.md, tech-core.md, tech-config.md, tech-connectors.md, tech-parsing.md]
updated: 2026-07-10
---

# Tech Spec: indexed

High-level architecture summary. Cross-cutting concerns + per-component pointers.
Component internals live in the branch docs below.

**For product decisions (what/why), see [product.md](product.md).**

---

## Component Specs

One tech branch doc per `src/indexed/` subpackage:

| Subpackage | Branch doc | Covers |
|-----------|-----------|--------|
| `src/indexed/cli/`, `src/indexed/mcp/` | [tech-app.md](tech-app.md) | CLI architecture, storage-mode, Rich UI, logging, MCP server |
| `src/indexed/core/` | [tech-core.md](tech-core.md) | engine, embedding, FAISS, persistence, search perf |
| `src/indexed/config/` | [tech-config.md](tech-config.md) | config resolution, .env hierarchy, storage layout, schema versioning |
| `src/indexed/connectors/` | [tech-connectors.md](tech-connectors.md) | connector protocol, implemented connectors, change tracking |
| `src/indexed/parsing/` | [tech-parsing.md](tech-parsing.md) | ParsingModule, Docling, tree-sitter |

`src/indexed/utils/` (logging, retry, batching) is a thin shared foundation — no
separate doc; helpers are imported by every layer. `src/indexed/protocols/` (typed
contracts + connector protocols, the leaf) has no separate doc either — covered
inline below (§ Protocols Subpackage) and in tech-core.md / tech-connectors.md.

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
| **uv** | 0.5+ | Package manager |
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

### Package Structure

Single package, one wheel (`indexed-sh`); no workspace, no `una`:

```text
indexed/
├── src/indexed/
│   ├── cli/                  # Typer app; composition.py is the single wiring site
│   ├── mcp/                  # FastMCP server
│   ├── core/                 # Indexing & search engine; facade in core/__init__.py
│   ├── connectors/           # Source connectors (files/jira/confluence/outline)
│   ├── config/                # Config management (ConfigService singleton)
│   ├── parsing/               # Shared parsing module (Docling, tree-sitter)
│   ├── protocols/             # Typed contracts + connector protocols — the leaf
│   └── utils/                 # Shared utilities (logging, retry, batching)
└── tests/                     # Test suite
```

**Build system:** a single `hatchling` build produces one wheel.

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
3. **Chunker** splits into token-window chunks (≤ embedder `max_seq_length`, 256 for the default model — never silently truncated; see [tech-parsing.md](tech-parsing.md))
4. **Embedder** generates vectors (384-dim via `all-MiniLM-L6-v2`)
5. **Indexer** builds FAISS index (`IndexFlatL2` default)
6. **Persister** saves to disk atomically

### Search Pipeline

```text
Query → Embedder → FAISS Search → Result Mapper → Formatter
```

1. **Embedder** converts query text to vector (same model as indexing)
2. **FAISS Search** finds K nearest neighbors (squared L2 distance in [0, 4]; lower = closer)
3. **Result Mapper** looks up chunks, documents, metadata
4. **Formatter** outputs as card/table/compact/JSON

---

## Testing Strategy

**Target:** >85% coverage on `core`/`connectors`/`config`/`parsing`/`protocols`/
`utils`. `cli`/`mcp` (UI chrome) are exempt from the gate — see § Post-Simplify
Structural Rules and `[tool.coverage.run]` in `pyproject.toml`.

```text
tests/
├── unit/              # tests/unit/{indexed,indexed_core,indexed_connectors,indexed_config,indexed_parsing,indexed_protocols,utils,scripts}/
├── system/            # integration tests
├── characterization/  # behavior-net harness (regression-guards fixed bugs)
└── benchmarks/        # performance tests
```

```bash
uv run pytest -q                              # all
uv run pytest tests/unit/indexed_core/ -q     # one subpackage
uv run pytest -q --cov=src/indexed --cov-report=html
```

---

## Build & Distribution

### Wheel

A single `hatchling` build packages `src/indexed/` into one wheel — no bundling
step, no per-package builds.

```bash
uv build --wheel --out-dir dist
# → dist/indexed_sh-<version>-py3-none-any.whl
uv run python scripts/validate_wheel.py dist/*.whl   # PyPI archive validator, also run in CI
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

### Post-Simplify Structural Rules

Promoted from the retired Feature 14 (Simplify) tech spec as of simplify/6 —
normative root rules from here on,
independent of Feature 14's own DONE/PLANNED status ([plan.md](plan.md) §
Feature Sequence). The single-package collapse, `check_imports.py` gate,
scoped coverage config, and one `AGENTS.md` are already live in the tree; the
remaining Simplify units (residual dead-code/test cleanup) converge the rest
of the codebase toward these same rules rather than establishing new ones.

- **One package, four module edges** (`cli`/`mcp` → `core`|`connectors`|`config`;
  `core ↛ connectors`; `connectors ↛ core`; `config`/`utils`/`parsing`/`protocols`
  never import up), enforced by `scripts/check_imports.py`. One `pyproject.toml`,
  one wheel (`indexed-sh`), no `una`, no per-package builds, no `sync_version.py`.
- **No phantom generality.** No abstraction (registry/factory/multi-impl loop)
  over a single implementation. One indexer, one progress protocol, no dead DTOs
  or re-export shims.
- **Behavior-only tests.** Keep behavior/system/benchmark tests + the
  characterization harness; no mechanism tests (registry membership, shims,
  protocol stubs, Rich markup, migration). **Coverage gate is scoped to
  `core`/`connectors`/`config`/`parsing`/`protocols`/`utils`; UI chrome
  (`cli`/`mcp`) is exempt** (see `[tool.coverage.run]` in `pyproject.toml`).
- **One root `AGENTS.md`** (≤100 lines); agent skills install from
  `skills-lock.json`, never vendored.

### Dependency Direction

```text
┌──────────────────────────────────────────────────────┐
│  CLI / MCP (src/indexed/cli/, src/indexed/mcp/)      │  ← UI only, thin commands
│  May import: core (facade), connectors.registry,     │
│  config, protocols, utils                            │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Core Engine (src/indexed/core/)                     │  ← Business logic
│  May import: protocols, config, utils                │
│  MUST NOT import: CLI, MCP, concrete connectors      │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Connectors (src/indexed/connectors/)                │  ← Data source adapters
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
- Missing/corrupt collections **fail loud**: they raise `IndexedError` and are
  **omitted from status** (never zero-filled into a fake-healthy placeholder); the
  CLI exits **non-zero** (via `exit_code_for`) with a clean message — never a raw
  traceback, never a success exit on failure
- The MCP boundary **envelopes every exception** (not only `IndexedError`) and
  surfaces per-collection failures in the result envelope — never a silent
  "0 matches" — and must not serve **stale** cached results after a re-index

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

### Protocols Subpackage (`indexed.protocols`)

Shared connector contracts, **typed data models**, and cross-layer DTOs live in the
**leaf** subpackage `src/indexed/protocols/` (import `indexed.protocols`) — the only
import-legal home, since `core`/`connectors`/`config` may not import one another but all
may import `protocols`. Engine-only DTOs stay in core.

- **Typed data contracts** (`protocols/models.py`): `Manifest`, `ConvertedDocument`,
  `Chunk`, `CollectionSearchResult` (+ `DocumentMatch`/`MatchedChunk`) and `SourceConfig`.
  They round-trip today's on-disk **camelCase JSON byte-stable** (fields declared in
  on-disk key order, dumped `by_alias=True`, `exclude_none=True`) — the on-disk v1 format
  is the **compatibility boundary**, so a v2 engine reads the same collections. The engine
  reads/writes these models, never `dict["stringKey"]`; a field mismatch is a mypy error,
  not a runtime `KeyError`.
- **Corrected connector protocols** (`protocols/connectors.py`): `DocumentReader` declares
  exactly what the engine calls — `get_number_of_documents` / `read_all_documents` /
  `get_reader_details`; `DocumentConverter` declares `convert`. A connector missing one is
  a mypy error, not a runtime `AttributeError`. `BaseConnector` also declares
  `from_manifest(manifest, config, *, storage_path) -> ConnectorRun` — each connector owns
  its manifest keys and incremental cutoff, so **core's update path has no per-source /
  `localFiles` branches**.
- `SourceConfig`, `ProgressUpdate`, `ProgressCallback`, `PhasedProgressCallback` (the
  progress callbacks are today's dual system; Feature 14 collapses them to one `Progress`
  protocol).

`core` and `connectors` both depend on `protocols`; neither imports the other's
concrete types for wiring.

### Core Facade & App Composition Root

**Core is consumed only through the `core.v1.engine` facade** — `create` / `update` /
`search` / `inspect` / `status` / `clear` / `collection_exists` (+ the shared models).
The facade (`engine/__init__.py`, lazy `__getattr__`) is the **v2 core-swap seam**: a v2
engine ships behind the same names over the same on-disk format and nothing above the
facade changes. The app never imports `core.v1.engine.services` / `factories` / `core`
directly (to mock a facade-resolved symbol in tests, patch the facade attribute).

**`src/indexed/cli/composition.py` is the single wiring site** — it folds in the
removed `bootstrap.py` + `runtime.py` + `connector_wiring.py`. It:

- builds the connector registry and hands the facade **two REQUIRED callables** —
  `connector_factory` (create-time) and `manifest_factory` (update-time). No
  `Callable | None` + `missing_wiring_error` on the happy path; a missing wiring is a
  `TypeError`/mypy error at the call site, not a runtime guard.
- owns `resolve_collections_context(mode_override)` — the **single** storage-path resolver
  for CLI and MCP — and calls `register_app_config` itself, so registered config specs
  survive the singleton reset a non-None `mode_override` forces. Do not revive heuristics
  like "prefer local if non-empty collections dir", and do not add a per-caller defensive
  re-register for callers that go through it.

Each connector's `from_manifest` owns its manifest keys, so core carries no per-type
branches; `composition.manifest_factory` is a one-line registry dispatch.

### Import-Graph CI

`scripts/check_imports.py` (also run in CI, alongside `scripts/check_sizes.py`)
AST-walks `src/indexed` and fails on forbidden edges — the four rules above,
expanded:

| From | Must NOT import |
|------|-----------------|
| `core` | `connectors`, `cli`, `mcp` |
| `connectors` | `core`, `cli`, `mcp` |
| `config`, `parsing`, `utils`, `protocols` | `core`, `connectors`, `cli`, `mcp` |

`cli`/`mcp` sit at the top of the stack and may import any subpackage — they have
no forbidden edge of their own. Run `python scripts/check_imports.py --self-test`
to verify a synthetic forbidden edge is still caught.

### HTTP Retry Policy

Transient HTTP statuses are centralized in `utils/retry.py`:

```python
TRANSIENT_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})
```

`execute_with_retry` re-raises immediately on non-transient HTTP errors (e.g. 404).
Connector readers use this helper — do not duplicate status-code tuples.

---

## Open Technical Questions

1. **Index sharding** — handle >10M documents? Shard by source? Date range? Needs benchmarking.
2. **Embedding versioning** — model update migration? Store model version in manifest? Auto re-index?
3. **Concurrent writes** — no locking on collection updates today. File locking? Atomic swap?
4. **Query caching** — cache query embeddings? Deduplicate identical queries? Invalidation?
5. **Connector reliability** — transient API failures: retry with backoff? Circuit breaker?
6. **Multi-user server mode** — DB instead of JSON files? PostgreSQL + pgvector? SQLite?
