# AGENTS.MD - Python Engineering Guide

**Last Updated:** 2026-02-06
**Repository:** indexed v0.1.0 (Python monorepo)

## Core Operating Principles

### 1. ASK → PLAN → CONFIRM → EXECUTE

**NEVER write code without approval.**

1. **ASK**: Clarify requirements, understand constraints, avoid assumptions
2. **PLAN**: Break down tasks, research patterns, present approach with reasoning
3. **CONFIRM**: Get explicit user approval before any implementation
4. **EXECUTE**: Implement step-by-step with clear explanations

### 2. Quality-First Engineering

- **KISS**: Keep It Simple, Stupid - prefer simplicity over complexity
- **Type Safety**: All code MUST pass mypy strict mode
- **Code Quality**: All commits MUST pass ruff checks (lint + format)
- **Test Coverage**: Maintain >85% coverage target
- **Performance**: Sub-second CLI startup times (lazy loading strategy)

### 3. Critical Constraints

- **ALWAYS run from PROJECT ROOT** - monorepo operations require this
- **ALWAYS use `uv run <command>`** - never manually activate virtual environments
- **ALWAYS run FULL test suite before push** - monorepo integrity is critical
- **ALWAYS commit `uv.lock`** - reproducible builds required
- **NEVER use `una sync`** - causes dependency conflicts
- **NEVER create files without necessity** - prefer editing existing files
- **NEVER proceed without user confirmation**
- **NEVER skip test coverage** - >85% is a hard requirement

## Tech Stack

### Core Technologies
```python
# Language & Runtime
Python 3.11+              # Minimum version required
uv 0.5+                   # Package manager (workspace support)
una                       # Monorepo wheel bundling

# Core Libraries
FAISS                     # Vector similarity search
sentence-transformers     # Embedding generation
Typer 0.15.1              # CLI framework
FastMCP                   # Model Context Protocol server
Pydantic 2.10             # Data validation

# Development Tools
ruff 0.9.1                # Linting + Formatting (replaces flake8/black)
mypy 1.14                 # Static type checking
pytest 8.3.4              # Testing framework
pytest-cov 6.0            # Coverage reporting
pre-commit 4.0            # Git hooks
```

### Package Manager Rules
```bash
# ONLY use uv - NEVER pip, pipenv, or poetry directly
uv sync                   # Install dependencies
uv sync --all-groups      # Install with dev dependencies
uv run <command>          # Run commands (ALWAYS use this)
uv run pytest -q          # Run tests
uv run ruff check .       # Lint code
uv run ruff format        # Format code
```

## Project Architecture

### Repository Structure
```
indexed/
├── AGENTS.md                          # You are here
├── README.md                          # User documentation
├── pyproject.toml                     # Workspace root config
├── uv.lock                            # Locked dependencies (ALWAYS commit)
│
├── apps/indexed/                      # Main CLI application & MCP server
│   ├── src/indexed/
│   │   ├── cli/                       # CLI commands (Typer)
│   │   ├── mcp/                       # MCP server implementation
│   │   └── main.py                    # Entry points
│   └── pyproject.toml
│
├── packages/
│   ├── indexed-core/                  # Core indexing & search engine
│   │   ├── src/core/
│   │   │   ├── indexing/              # FAISS indexing
│   │   │   ├── search/                # Search service
│   │   │   └── models/                # Domain models
│   │   └── pyproject.toml
│   │
│   ├── indexed-connectors/            # Document source adapters
│   │   ├── src/connectors/
│   │   │   ├── jira/                  # Jira integration
│   │   │   ├── confluence/            # Confluence integration
│   │   │   └── files/                 # File system integration
│   │   └── pyproject.toml
│   │
│   ├── indexed-config/                # Configuration management
│   │   ├── src/indexed_config/
│   │   │   ├── service.py             # ConfigService (singleton)
│   │   │   └── models.py              # Pydantic models
│   │   └── pyproject.toml
│   │
│   └── utils/                         # Cross-cutting utilities
│       ├── src/utils/
│       │   ├── logging.py             # Logging utilities
│       │   ├── retry.py               # Retry logic
│       │   └── batching.py            # Batch processing
│       └── pyproject.toml
│
└── tests/                             # Comprehensive test suite
    ├── unit/                          # Package-specific unit tests
    ├── system/                        # Integration tests
    └── benchmarks/                    # Performance benchmarks
```

### Package Responsibilities

| Package | Purpose | Key Responsibility |
|---------|---------|-------------------|
| **indexed** (app) | CLI & MCP Server | User interaction, command parsing, AI integration |
| **indexed-core** | Engine | Document indexing, FAISS search, persistence |
| **indexed-connectors** | Adapters | Read from Jira, Confluence, files |
| **indexed-config** | Configuration | TOML config, environment merging, validation |
| **utils** | Utilities | Logging, retry logic, batching, performance helpers |

## Development Workflows

### Common Commands

```bash
# Development Setup
uv sync --all-groups              # Install all dependencies + dev tools
uv run pre-commit install --hook-type pre-commit --hook-type pre-push

# Code Quality
uv run ruff check . --fix         # Lint with auto-fix
uv run ruff format                # Format code
uv run mypy src/                  # Type check

# Testing
uv run pytest -q                  # Run tests (quiet)
uv run pytest -v                  # Run tests (verbose)
uv run pytest -q --cov=src --cov-report=html  # With coverage
uv run pytest tests/unit/indexed_core/ -q     # Specific package
uv run pytest tests/benchmarks/ -q --benchmark-only  # Benchmarks only

# Running the CLI
uv run indexed --help             # Show help
uv run indexed index create my-docs --source files --source-path ./docs
uv run indexed index search "query" --collection my-docs
uv run indexed index list         # List all collections

# Running the MCP Server
uv run indexed-mcp run            # Stdio mode (Claude Desktop)
uv run indexed-mcp run --log-level DEBUG
uv run indexed-mcp run --transport http --port 8000

# Building
uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/indexed
```

### Git Commit Standards

**ABSOLUTE FORMAT (50 characters max, one line only):**
```bash
[type](optional-scope): imperative subject

# Examples:
feat(core): add FAISS index caching
fix(mcp): resolve search timeout issue
refactor(connectors): simplify reader interface
perf(indexing): optimize embedding batch size
chore(deps): update sentence-transformers
test(search): add integration tests
```

**Allowed Types:**
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code change (no bug fix or feature)
- `perf`: Performance improvement
- `style`: Formatting only (no logic changes)
- `test`: Add/update tests
- `docs`: Documentation only
- `build`: Build system changes
- `ci`: CI/CD configuration
- `chore`: Housekeeping (NOT code changes)
- `revert`: Revert previous commit

**Rules:**
- MUST be imperative mood ("add", NOT "added" or "adds")
- MUST be lowercase (except proper nouns/acronyms)
- MUST NOT exceed 50 characters total
- MUST NOT have trailing period
- MUST NOT have body or footer

## Architecture Deep Dive

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
│  Config, Connectors, Utils              │
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

## Configuration System

### Configuration Hierarchy (increasing priority)

1. **Pydantic defaults** (lowest)
2. **Global config** (`~/.indexed/config.toml`)
3. **Workspace config** (`./.indexed/config.toml`)
4. **Environment variables** (`INDEXED__section__key=value`)
5. **CLI arguments** (highest)

### Storage Architecture

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

### Example Configuration

```toml
# ~/.indexed/config.toml
[general]
log_level = "INFO"
storage_mode = "global"

[indexing]
chunk_size = 512
chunk_overlap = 50
model_name = "all-MiniLM-L6-v2"

[search]
top_k = 10
similarity_threshold = 0.7

[jira]
server_url = "https://company.atlassian.net"
# Credentials go in .env: INDEXED__jira__api_token=xxx
```

## Key Design Patterns

### 1. Protocol-Based Extensibility
All connectors implement `BaseConnector` protocol:
```python
from typing import Protocol, Iterator
from core.models import Document

class BaseConnector(Protocol):
    def read_documents(self) -> Iterator[Document]:
        """Fetch documents from source."""
        ...

    def convert_documents(self, docs: Iterator[Document]) -> Iterator[Document]:
        """Transform documents into chunks."""
        ...
```

### 2. Configuration-Driven Behavior
```python
from indexed_config import ConfigService

# Singleton pattern - consistent config throughout app
config = ConfigService.get_instance()
chunk_size = config.indexing.chunk_size
model_name = config.indexing.model_name
```

### 3. Lazy Loading for Performance
```python
# Heavy dependencies are lazy-loaded
def get_embedder():
    """Lazy load sentence transformers (500ms+ import cost)."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)

# Result: CLI startup <1s even with PyTorch/Transformers
```

### 4. Reader/Converter Separation
```python
class JiraConnector:
    def __init__(self):
        self.reader = JiraDocumentReader()
        self.converter = JiraDocumentConverter()

    def fetch_and_convert(self) -> Iterator[Document]:
        raw_docs = self.reader.read()
        return self.converter.convert(raw_docs)
```

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

### Testing Patterns

```python
# Unit test example
import pytest
from core.search import SearchService

def test_search_service_basic(tmp_path):
    """Test basic search functionality."""
    service = SearchService(storage_path=tmp_path)
    results = service.search("test query", collections=["docs"])
    assert len(results) > 0
    assert results[0].score > 0.5

# Fixture example (conftest.py)
@pytest.fixture
def sample_collection(tmp_path):
    """Create a sample collection for testing."""
    from core.indexing import DocumentCollectionCreator

    creator = DocumentCollectionCreator(storage_path=tmp_path)
    collection = creator.create(
        name="test-docs",
        documents=[Document(id="1", text="Sample document")]
    )
    return collection
```

### Coverage Requirements
- **Target:** >85% coverage
- **Measured on:** Installed packages (not source paths)
- **Packages:** indexed, core, connectors, indexed_config, utils

```bash
# Run with coverage
uv run pytest -q --cov=src --cov-report=html

# View report
open htmlcov/index.html
```

## MCP (Model Context Protocol) Integration

The MCP server exposes indexed collections to AI agents (Claude, Cursor, Cline):

### Tools Provided
```python
# Available MCP tools
search(query: str, collection: str) -> List[SearchResult]
list_collections() -> List[str]
collection_status(name: str) -> CollectionMetadata
```

### Transport Modes

```bash
# Stdio mode (Claude Desktop, Cline)
uv run indexed-mcp run

# HTTP server
uv run indexed-mcp run --transport http --host 127.0.0.1 --port 8000

# SSE (Server-Sent Events)
uv run indexed-mcp run --transport sse

# With logging
uv run indexed-mcp run --log-level DEBUG
```

### Claude Desktop Integration

```json
// ~/.config/claude/claude_desktop_config.json
{
  "mcpServers": {
    "indexed": {
      "command": "uv",
      "args": ["--directory", "/path/to/indexed", "run", "indexed-mcp", "run"],
      "env": {
        "INDEXED__general__log_level": "INFO"
      }
    }
  }
}
```

## Claude Code Skills

**CRITICAL:** Use available skills as quality gates in your workflow.

### Available Skills

**1. feature-dev:feature-dev** 🏗️ **USE FOR COMPLEX FEATURES**
- **Purpose**: Guided feature development with codebase understanding
- **When to use**:
  - Multi-file feature implementations
  - Need codebase pattern analysis first
  - Complex architectural decisions required
- **Example**: "Implement new Slack connector with authentication"

**2. find-skills** 🔍 **USE TO DISCOVER MORE**
- **Purpose**: Discover and install additional Claude Code skills
- **When to use**:
  - Looking for specific functionality
  - Want to extend Claude's capabilities
- **Example**: "Find a skill for Python testing best practices"

**3. keybindings-help** ⌨️ **USE FOR CUSTOMIZATION**
- **Purpose**: Customize keyboard shortcuts in Claude Code
- **When to use**:
  - Want to modify default keybindings
  - Need to add chord shortcuts
- **Example**: "Rebind submit to Ctrl+Enter"

### Skill Integration Workflow

```bash
# RECOMMENDED WORKFLOW FOR NEW FEATURES:

1. ASK phase:
   - Clarify requirements
   - If complex feature → consider feature-dev:feature-dev skill

2. PLAN phase:
   - Research existing patterns
   - Read relevant CURSOR.md files in packages/
   - Break down into testable units

3. CONFIRM phase:
   - Present approach to user
   - Get approval with skill recommendations

4. EXECUTE phase:
   - Implement code
   - Run ruff: uv run ruff check . --fix && uv run ruff format
   - Run mypy: uv run mypy src/
   - Run tests: uv run pytest -q --cov=src
   - Verify coverage: >85% required

5. REVIEW phase:
   - Final quality checks
   - Commit with proper format
```

## Best Practices

### DO ✅
- Use type hints extensively (mypy strict mode)
- Follow protocol-based design for extensibility
- Leverage Pydantic for data validation
- Use lazy loading for heavy dependencies (ML libraries)
- Write comprehensive tests (>85% coverage)
- Use ruff for both linting and formatting
- Follow configuration hierarchy strictly
- Use `uv run` for all commands
- Run from PROJECT ROOT always
- Commit `uv.lock` to version control
- Ask questions before implementing
- Get user approval before coding
- Use skills as quality gates

### DON'T ❌
- NEVER use pip/pipenv/poetry directly - ONLY uv
- NEVER manually activate virtual environments
- NEVER use `una sync` (causes conflicts)
- NEVER run commands outside PROJECT ROOT
- NEVER skip tests before push
- NEVER exceed 50 chars in commit messages
- NEVER create files without necessity
- NEVER proceed without user confirmation
- NEVER import heavy ML libraries at module level (lazy load them)
- NEVER hardcode configuration values (use config system)
- NEVER skip type hints (mypy strict mode required)
- NEVER commit code that fails ruff checks

## Performance Optimization

### CLI Startup Time
**Target:** <1 second despite PyTorch/Transformers dependencies

**Strategies:**
1. **Lazy loading** of heavy dependencies (ML libraries)
2. **Deferred initialization** of services (only when commands run)
3. **Minimal imports** at module level
4. **Configuration caching** to avoid re-parsing

```python
# BAD - imports immediately (500ms+ cost)
from sentence_transformers import SentenceTransformer

# GOOD - imports only when needed
def get_embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)
```

### FAISS Indexing
- Batch embedding generation (default: 32)
- Use appropriate FAISS index type (Flat for <100k docs)
- Cache searchers for repeated queries
- Persist indices to disk after creation

## Troubleshooting

### Common Issues

**Tests failing:**
- Run from PROJECT ROOT: `cd /path/to/indexed && uv run pytest`
- Check coverage: `uv run pytest -q --cov=src --cov-report=html`
- Verify all dependencies installed: `uv sync --all-groups`

**Ruff/mypy errors:**
- Auto-fix ruff: `uv run ruff check . --fix && uv run ruff format`
- Check mypy: `uv run mypy src/`
- Review error output and fix type issues

**Configuration not loading:**
- Check config hierarchy (CLI args > env vars > workspace config > global config)
- Verify TOML syntax: `uv run python -c "import tomli; tomli.load(open('.indexed/config.toml', 'rb'))"`
- Check environment variables: `printenv | grep INDEXED`

**MCP server not connecting:**
- Verify command in Claude Desktop config
- Check logs: `uv run indexed-mcp run --log-level DEBUG`
- Test manually: `uv run indexed-mcp run` and check output

**Build failures:**
- Build from PROJECT ROOT: `cd /path/to/indexed`
- Use correct command: `uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/indexed`
- Check for missing dependencies: `uv sync --all-groups`

## Quick Reference

### Essential Commands
```bash
uv sync --all-groups              # Install all dependencies
uv run pytest -q                  # Run tests
uv run ruff check . --fix         # Lint + auto-fix
uv run ruff format                # Format code
uv run mypy src/                  # Type check
uv run indexed --help             # CLI help
uv run indexed-mcp run            # MCP server
```

### Essential Patterns
```python
# Configuration
from indexed_config import ConfigService
config = ConfigService.get_instance()

# Lazy loading
def get_heavy_dependency():
    from heavy_library import HeavyClass
    return HeavyClass()

# Protocol implementation
from typing import Protocol
class BaseConnector(Protocol):
    def read_documents(self) -> Iterator[Document]: ...

# Pydantic models
from pydantic import BaseModel, Field
class SearchConfig(BaseModel):
    top_k: int = Field(default=10, ge=1, le=100)
```

### File Locations
```
CLI Commands:       apps/indexed/src/indexed/cli/
MCP Server:         apps/indexed/src/indexed/mcp/
Core Engine:        packages/indexed-core/src/core/
Connectors:         packages/indexed-connectors/src/connectors/
Configuration:      packages/indexed-config/src/indexed_config/
Tests:              tests/unit/, tests/system/, tests/benchmarks/
Package Docs:       packages/*/CURSOR.md
```

### Package Import Patterns
```python
# From CLI/MCP layer
from core.search import SearchService
from core.indexing import DocumentCollectionCreator
from connectors.jira import JiraConnector
from indexed_config import ConfigService

# From core layer
from indexed_config.models import IndexingConfig
from connectors.base import BaseConnector
from utils.logging import setup_logging

# Testing
import pytest
from core.models import Document, SearchResult
```

---

**Remember:** ASK → PLAN → CONFIRM → EXECUTE. Quality over speed. KISS principle always.
