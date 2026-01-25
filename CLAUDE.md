# Indexed - Project Overview & Architecture Guide

**Indexed** is a privacy-first, semantic document search platform that enables AI agents and LLMs to access institutional knowledge from multiple data sources without compromising data privacy.

## What is Indexed?

- **Core Purpose:** Index documents from Jira, Confluence, and local files for semantic search
- **Privacy Model:** 100% local processing with zero external data transmission
- **AI Integration:** Expose search capabilities via Model Context Protocol (MCP) server
- **Architecture:** Python monorepo with modular, extensible design

## Quick Facts

- **Language:** Python 3.11+
- **Package Manager:** uv (with workspace support)
- **Build System:** una (monorepo wheel bundling)
- **Core Technologies:** FAISS, sentence-transformers, Typer, FastMCP, Pydantic
- **Test Coverage Target:** >85%
- **License:** Faire Use license

## Repository Structure

```
indexed/
├── CURSOR.md                          # You are here
├── README.md                          # User documentation
├── pyproject.toml                     # Workspace root config
├── uv.lock                            # Locked dependencies
│
├── apps/indexed/                      # Main CLI application & MCP server
│   └── CURSOR.md                      # CLI/MCP implementation guide
│
├── packages/
│   ├── indexed-core/                  # Core indexing & search engine
│   │   └── CURSOR.md                  # Engine architecture guide
│   ├── indexed-connectors/            # Document source adapters
│   │   └── CURSOR.md                  # Connector system guide
│   ├── indexed-config/                # Configuration management
│   │   └── CURSOR.md                  # Config system guide
│   └── utils/                         # Cross-cutting utilities
│       └── CURSOR.md                  # Utilities guide
│
├── tests/                             # Comprehensive test suite
│   ├── unit/                          # Package-specific unit tests
│   ├── system/                        # Integration tests
│   └── benchmarks/                    # Performance benchmarks
│
├── docs/                              # Architecture & design docs
├── .cursor/rules/                     # AI agent instruction rules
│   ├── core.mdc                       # Mandatory coding protocol
│   ├── environment.mdc                # Dev environment standards
│   ├── context.mdc                    # Product goals & scope
│   ├── product-requirements.mdc       # Product PRD
│   ├── tech/architecture.mdc          # System architecture
│   ├── tech/performance-optimization.mdc  # Python optimization guide
│   └── actions/commit.mdc             # Git commit standards
└── Dockerfile                         # Docker deployment
```

## Core Packages at a Glance

| Package | Purpose | Key Responsibility |
|---------|---------|-------------------|
| **indexed** (app) | CLI & MCP Server | User interaction, command parsing, AI integration |
| **indexed-core** | Engine | Document indexing, FAISS search, persistence |
| **indexed-connectors** | Adapters | Read from Jira, Confluence, files |
| **indexed-config** | Configuration | TOML config, environment merging, validation |
| **utils** | Utilities | Logging, retry logic, batching, performance helpers |

## Development Workflow

### Quick Start

```bash
# Install all dependencies (including dev tools)
uv sync --all-groups

# Run tests
uv run pytest -q

# Check code quality
uv run ruff check . --fix
uv run ruff format

# Run CLI
uv run indexed --help

# Run MCP server
uv run indexed-mcp --help
```

### Common Tasks

**Create a new collection (index files):**
```bash
uv run indexed index create my-docs --source files --source-path ./documents
```

**Search across collections:**
```bash
uv run indexed index search "how to deploy" --collection my-docs
```

**Run full test suite:**
```bash
uv run pytest -q --cov=src --cov-report=html
```

**Build distributable wheel:**
```bash
uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/indexed
```

**Run MCP server for Claude Desktop:**
```bash
uv run indexed-mcp run --log-level INFO
```

## Architecture Overview

### Three-Layer Design

```
┌─────────────────────────────────────────┐
│     CLI Layer (indexed/)                │
│  Commands, UI, MCP Server, Logging      │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│    Service Layer (indexed-core/)        │
│ Orchestration, Validation, Factories    │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│     Engine Layer (indexed-core/)        │
│ FAISS, Embeddings, Persistence          │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  Infrastructure Layer                   │
│  Config (indexed-config/)               │
│  Connectors (indexed-connectors/)       │
│  Utils (utils/)                         │
└─────────────────────────────────────────┘
```

### Indexing Pipeline

```
CLI Command
    ↓
ConfigService (load & validate TOML config)
    ↓
Connector (Jira/Confluence/Files)
    ├─ DocumentReader (fetch raw documents)
    ├─ DocumentConverter (chunk documents)
    ↓
DocumentCollectionCreator
    ├─ SentenceEmbedder (generate embeddings)
    ├─ FaissIndexer (create vector index)
    └─ DiskPersister (save to disk)
    ↓
Collection ready for search
```

### Search Pipeline

```
User Query
    ↓
SearchService.search(query, collections)
    ├─ For each collection:
    │   ├─ Load cached searcher (or create new)
    │   ├─ Embed query text
    │   ├─ FAISS similarity search
    │   └─ Map results to document chunks
    ↓
Format & display results (JSON, table, or cards)
```

## Storage Architecture

```
~/.indexed/                      # Global storage (default)
├── config.toml                  # Configuration
├── .env                         # Sensitive credentials
└── data/
    └── collections/
        └── {collection-name}/
            ├── manifest.json    # Metadata
            ├── documents.json   # Document info
            ├── chunks.json      # Chunked text
            └── index.faiss      # FAISS vector index
```

**Storage Modes:**
- **Global:** `~/.indexed/` (default, shared across projects)
- **Local:** `./.indexed/` (project-specific, overrides global)

## Configuration System

Configuration follows a strict hierarchy (increasing priority):

1. **Pydantic defaults** (lowest)
2. **Global config** (`~/.indexed/config.toml`)
3. **Workspace config** (`./.indexed/config.toml`)
4. **Environment variables** (`INDEXED__section__key=value`)
5. **CLI arguments** (highest)

All configuration is validated with Pydantic models. Sensitive fields (tokens, passwords, API keys) are automatically routed to `.env`.

## Key Design Patterns

### 1. **Protocol-Based Extensibility**
All connectors implement `BaseConnector` protocol, enabling new data sources without modifying core code.

### 2. **Configuration-Driven Behavior**
All behavior is controlled by TOML config + environment variables, not hardcoded values.

### 3. **Reader/Converter Separation**
Each connector separates document fetching (Reader) from transformation (Converter).

### 4. **Lazy Loading for Performance**
Heavy dependencies (ML libraries) are lazy-loaded to achieve sub-second CLI startup times.

### 5. **Singleton Pattern**
ConfigService uses singleton pattern to maintain consistent configuration throughout application lifetime.

## Testing Strategy

### Test Organization

```
tests/
├── conftest.py                 # Shared fixtures
├── unit/
│   ├── indexed/               # CLI tests
│   ├── indexed_core/          # Engine tests
│   ├── indexed_connectors/    # Connector tests
│   ├── indexed_config/        # Config system tests
│   └── utils/                 # Utilities tests
├── system/                     # Integration tests
└── benchmarks/                 # Performance tests
```

### Running Tests

```bash
# Full test suite with coverage
uv run pytest -q --cov=src --cov-report=html

# Specific package
uv run pytest tests/unit/indexed_core/ -q

# With verbose output
uv run pytest -v

# Run benchmarks
uv run pytest tests/benchmarks/ -q --benchmark-only
```

### Coverage Goals
- **Target:** >85% coverage
- **Measured on:** Installed packages (not source paths)
- **Packages:** indexed, core, connectors, indexed_config, utils

## Code Quality Standards

### Linting & Formatting (ruff)

```bash
# Check for issues
uv run ruff check .

# Auto-fix issues
uv run ruff check . --fix

# Format code
uv run ruff format
```

**Standards:**
- Line length: 100 characters
- Target Python: 3.11+
- Rules: F (Pyflakes), E (errors), W (warnings), I (imports)

### Type Checking (mypy)

```bash
uv run mypy src/
```

**Requirements:**
- Disallow untyped definitions
- Warn on return type issues

### Pre-commit Hooks

Git hooks run automatically before commits/pushes:

```bash
# Install hooks
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
```

- **Pre-commit:** ruff check & format
- **Pre-push:** full test suite + wheel build verification

## MCP (Model Context Protocol) Integration

The MCP server exposes indexed collections to AI agents (Claude, Cursor, Cline):

**Tools Provided:**
- `search(query, collection)` - Search collections
- `list_collections()` - List available collections
- `collection_status(name)` - Get collection metadata

**Transport Modes:**
- **stdio** (default) - Claude Desktop, Cline
- **http** - HTTP server with JSON API
- **sse** - Server-Sent Events for streaming

**Running the MCP Server:**
```bash
# Stdio mode (Claude Desktop)
uv run indexed-mcp run

# HTTP server
uv run indexed-mcp run --transport http --host 127.0.0.1 --port 8000

# With logging
uv run indexed-mcp run --log-level DEBUG
```

## Dependency Management

All dependencies are managed via `uv` with a locked `uv.lock` file:

```bash
# Sync dependencies
uv sync

# Sync including dev dependencies
uv sync --all-groups

# Update all dependencies
uv sync --upgrade

# Update specific dependency
uv sync --upgrade-package pytest
```

**Always commit `uv.lock`** to version control for reproducible builds.

## Building & Distribution

The project builds to a single distributable wheel containing all workspace packages:

```bash
# Build from PROJECT ROOT
uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/indexed

# Result: dist/indexed-{version}-py3-none-any.whl
# Contains: indexed CLI + all bundled packages (indexed-core, indexed-connectors, indexed-config, utils)
```

**Docker Deployment:**
```dockerfile
FROM python:3.11-slim
COPY dist dist
RUN pip install dist/*.whl
ENTRYPOINT ["indexed-mcp"]
```

## Performance Optimization

For Python CLI optimization insights, see `.cursor/rules/tech/performance-optimization.mdc`.

Key strategies used:
- **Lazy loading** of heavy dependencies (ML libraries)
- **Deferred initialization** of services (only when commands run)
- **Minimal imports** at module level
- **Configuration caching** to avoid re-parsing

Result: Sub-second CLI startup times despite dependencies like PyTorch and Transformers.

## Important Rules & Standards

### Git Commits
Strict conventional commit format (see `.cursor/rules/actions/commit.mdc`):
```
[type](scope): subject
```
- **50 characters maximum**
- **Imperative mood** ("add", not "added")
- **No body or footer**

### Environment Setup
**MANDATORY:** Always use `uv run <command>`. Never manually activate virtual environments.

### Monorepo Operations
- **ALWAYS run from PROJECT ROOT**
- **ALWAYS run FULL test suite before push**
- **NEVER use `una sync`** (causes conflicts)
- **ALWAYS commit `uv.lock`**

### Code Quality Gates
- **Must pass:** ruff check + mypy
- **Must achieve:** >85% test coverage
- **Must use:** Clear design patterns and separation of concerns

## Package-Specific Documentation

For detailed documentation on each package, see:

- **[apps/indexed/CURSOR.md](apps/indexed/CURSOR.md)** - CLI & MCP Server implementation
- **[packages/indexed-core/CURSOR.md](packages/indexed-core/CURSOR.md)** - Core engine architecture
- **[packages/indexed-connectors/CURSOR.md](packages/indexed-connectors/CURSOR.md)** - Connector system
- **[packages/indexed-config/CURSOR.md](packages/indexed-config/CURSOR.md)** - Configuration management
- **[packages/utils/CURSOR.md](packages/utils/CURSOR.md)** - Utilities & helpers

## Further Reference

- **[.cursor/rules/](./cursor/rules/)** - Detailed standards for code, commits, environment, and architecture
- **[docs/](./docs/)** - Architecture documentation
- **[README.md](./README.md)** - User-facing documentation

---

**Last Updated:** January 24, 2026
