---
type: entrypoint
scope: tech
children: [tech-app.md, tech-core.md, tech-config.md, tech-connectors.md, tech-parsing.md]
updated: 2026-07-12
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

### CI Benchmarking

Performance regressions are caught in CI, not via local scripts. The former
`.benchmarks/benchmark_baseline.py` / `benchmark_compare.py` (baseline capture +
diff logic) were deleted and replaced by the GitHub Marketplace action
[`pytest Benchmark Baseline Check`](https://github.com/marketplace/actions/pytest-benchmark-baseline-check)
(`lennardzuendorf/pytest-bench-action`), wired in
`.github/workflows/python-benchmark.yml`.

The action runs `tests/system` + `tests/benchmarks` with `--benchmark-only`,
compares against a per-branch JSON baseline committed under
`.benchmarks/baselines/` (the general `.benchmarks/*.json` ignore carries a
`!baselines/` exception), posts one PR comment per run (deletes any prior bot
comment matching the report header before posting, so re-runs don't spam the
thread), and fails the job on a tolerance-exceeding regression. Trigger is
`pull_request` only (no `push` trigger) — the action checks out the PR's own
head branch, and when drift exceeds `update-tolerance` it stages a baseline
commit directly on the PR branch (`[skip ci]`, same-repo PRs only), which
lands on the target branch automatically when the PR merges. A `concurrency`
group (keyed on PR number, `cancel-in-progress: true`) prevents overlapping
runs from racing to push that staged commit.

Configured in this repo via `cross-branch-tolerance: 20`, `update-tolerance: 5`,
and a per-test `threshold-map` (max seconds per benchmark name substring). A
regression can be waived per-PR via the `benchmark-override` label
(`override-label`, explicitly set here) — the regression still shows in the
PR comment but doesn't fail the job; the repo-wide tolerance is untouched.

Pinned to an exact release tag (`@v1.0.2`), not the floating `@v1` major tag —
the floating tag raced with upstream's own release-automation retagging and
briefly 404'd mid-release (`unable to find version v1`). Bump the pin by hand
on new releases instead.

**Resolved (v1.0.0):** comparability used to key on the runner hostname
(`machine_info.node`), which GitHub-hosted runners randomize per job, so
cross-run comparisons false-positived as regressions. `v1.0.0` gates on a
CPU/system fingerprint instead (`cpu.brand_raw` + arch + core count + `system`),
so `ubuntu-latest` runs on the same CPU model compare cleanly; a genuine
hardware mismatch now skips with `comparison-skipped` (or hard-fails if
`enforce-same-node: "true"`, unset here) instead of hard-failing by default.
Not configured in this repo: `enforce-same-node` (defaults `"false"`, skip not fail on hardware mismatch).

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
7. **CI benchmark runner stability** — resolved by `pytest-bench-action`'s
   CPU-fingerprint gate (see tech.md § CI Benchmarking). `override-label` now
   configured. Still open: adopt `enforce-same-node: "true"`, or stay on the
   skip-not-fail default (hosted runners only)?
