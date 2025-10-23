# Tech Stack & Coding Rules

## Current Tech Stack

### Core Framework & Language
- **Python 3.10+** - Primary language
- **uv** - Package management and environment (MANDATORY - see development rules)
- **Type Hints** - Full type coverage with mypy

### Package Management (CRITICAL)
**ALWAYS use `uv run <command>` - NEVER manually activate environments**

```bash
# ✅ CORRECT - Use uv run
uv run indexed-cli --help
uv run pytest
uv run ruff check .

# ❌ WRONG - Don't activate manually
source venv/bin/activate
python -m indexed_cli.app
```

### Vector Search & Embeddings

**Current Implementation:**
- `faiss-cpu>=1.11.0` - Vector similarity search (local)
- `sentence-transformers>=5.0.0` - Local embeddings (primary)

**Phase 2 Additions:**
- OpenAI embeddings - Cloud option via API
- Voyage AI embeddings - Cloud option via API
- Multiple provider support through abstraction

### Document Processing
- `unstructured[all-docs]>=0.18.5` - Document parsing (20+ formats)
- `langchain>=0.3.26` - Document utilities
- `bs4>=0.0.2` - HTML parsing

### Atlassian Integration
- `atlassian-python-api>=4.0.7` - Unified client for Jira, Confluence, and Bitbucket
  - **Migration from jira-python**: Consolidated dependency for strategic consistency
  - Supports both Cloud (username/password + cloud=True) and Server/DC (token or username/password + cloud=False)
  - Uses `jql()` method with `start`/`limit` pagination instead of `search_issues()` with `startAt`/`maxResults`

### Configuration & Validation
- `pydantic>=2.5.0` - Data validation and settings
- `pydantic-settings>=2.2.1` - Configuration management
- `platformdirs>=4.2.0` - Cross-platform path management
- TOML format for configuration files

### CLI & User Interface
- `typer>=0.12.3` - CLI framework
- `rich>=13.0.0` - Enhanced terminal UI with colors, tables, progress bars, spinners
- `loguru>=0.7.0` - Structured logging with Rich integration

### MCP Integration
- `mcp>=1.13.0` - MCP protocol
- `fastmcp>=2.11.3` - Fast MCP server implementation

### Testing & Quality
- `pytest>=8.4.1` - Testing framework
- `pytest-cov>=4.1.0` - Coverage reporting
- `pytest-mock>=3.14.1` - Mocking utilities
- `mypy>=1.17.1` - Static type checking
- `ruff>=0.12.10` - Linting and formatting

## Architecture Patterns

### Layered Architecture

```
┌─────────────────────────────────────┐
│         CLI Layer                   │
│  (Typer commands, UI)              │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│      Controller Layer               │
│  (IndexController, SearchController)│
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│       Service Layer                 │
│  (IndexingService, SearchService,   │
│   EmbeddingService, StorageService) │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│    Infrastructure Layer             │
│  (Connectors, Storage, Config)      │
└─────────────────────────────────────┘
```

### Dependency Injection
- **ServiceFactory** creates and wires all dependencies
- Controllers receive services via constructor
- Services receive infrastructure components via constructor
- No service creates its own dependencies

```python
# Factory creates everything
factory = ServiceFactory.create_from_config(config)
index_controller = factory.create_index_controller()
search_controller = factory.create_search_controller()

# Controllers have all dependencies injected
class IndexController:
    def __init__(
        self,
        indexing_service: IndexingService,
        config: IndexConfig
    ):
        self.indexing_service = indexing_service
        self.config = config
```

### Configuration-Driven Design
- All behavior controlled by config files (TOML)
- Pydantic models for validation
- Environment variable overrides
- Hierarchical: global → workspace → command-line

## Coding Standards

### Type Safety
**REQUIRED:** Type hints on all functions and methods

```python
# ✅ Good
def search(
    query: str, 
    top_k: int = 10
) -> List[SearchResult]:
    pass

# ❌ Bad
def search(query, top_k=10):
    pass
```

### Error Handling
**REQUIRED:** Explicit error handling with custom exceptions

```python
# ✅ Good
try:
    documents = connector.read_documents()
except ConnectorError as e:
    logger.error(f"Failed to read documents: {e}")
    raise IndexingError(f"Document reading failed: {e}") from e

# ❌ Bad
documents = connector.read_documents()  # No error handling
```

### Logging
**REQUIRED:** Loguru for all logging (no Python stdlib logging)

**Architecture:**
- Core services use Loguru directly
- Rich formatting for console output
- Three display modes:
  - **Default (WARNING)**: Clean output, INFO logs captured by spinner
  - **Verbose (--verbose)**: Rich-formatted INFO logs with cyan styling
  - **Debug (--log-level=DEBUG)**: Extended DEBUG logs with source location

```python
from loguru import logger

# ✅ Good - Use Loguru
logger.info(f"Found {count} collections: {', '.join(names)}")
logger.debug(f"Candidate directories: {sorted(dirs)}")
logger.error(f"Failed to process: {error}")

# ❌ Bad - Don't use Python logging
import logging
logging.info("message")  # NO!

# ❌ Bad - Don't use print
print(f"Processing {item}")  # NO!
```

**Log Message Guidelines:**
- Keep messages user-friendly and concise
- Use f-strings for clarity
- Include relevant context (file names, counts, etc.)
- Use visual indicators: ✓ for success, relevant emojis sparingly

```python
# Good examples
logger.info(f"Found {len(collections)} collections: {', '.join(collections)}")
logger.info(f'Searching "{query}" across {num} collections')
logger.info(f"✓ {collection}: {count} documents")
```

### Docstrings
**REQUIRED:** Docstrings for all public classes and methods

```python
# ✅ Good
def embed_batch(self, texts: List[str]) -> np.ndarray:
    """Generate embeddings for multiple texts.
    
    Args:
        texts: List of text strings to embed
        
    Returns:
        Numpy array of shape (len(texts), embedding_dim)
        
    Raises:
        EmbeddingError: If embedding generation fails
    """
    pass
```

### Testing
**REQUIRED:** Tests for all new functionality

```python
# Test structure
def test_search_returns_results():
    # Arrange
    service = create_test_service()
    
    # Act
    results = service.search("test query")
    
    # Assert
    assert len(results) > 0
    assert all(isinstance(r, SearchResult) for r in results)
```

## File Organization

### Package Structure
```
packages/indexed-core/src/index/
├── controllers/         # Request handling, orchestration
├── services/           # Business logic
├── storage/            # Storage implementations
├── connectors/         # Data source connectors
├── config/             # Configuration management
├── models/             # Data models
└── utils/              # Shared utilities

apps/indexed-cli/src/indexed_cli/
├── commands/           # CLI command implementations
├── engines/            # Engine selection logic
└── server/             # MCP server
```

### Naming Conventions
- **Classes**: PascalCase (`IndexController`, `EmbeddingService`)
- **Functions/Methods**: snake_case (`create_index`, `embed_text`)
- **Constants**: UPPER_SNAKE_CASE (`DEFAULT_CHUNK_SIZE`)
- **Private**: Leading underscore (`_internal_method`)

## Development Workflow

### Required Commands

```bash
# Setup
uv sync --all-groups

# Run CLI
uv run indexed-cli --help

# Run tests
uv run pytest -q

# Linting
uv run ruff check .
uv run ruff check . --fix

# Formatting
uv run ruff format

# Type checking
uv run mypy packages/indexed-core/src
```

### Git Workflow
- Branch naming: `feature/description`, `fix/description`, `phase2-name`
- Commit messages: Follow conventional commits
  - `feat:` New features
  - `fix:` Bug fixes
  - `refactor:` Code refactoring
  - `test:` Test updates
  - `docs:` Documentation
  - `chore:` Build/tooling

### Code Review Checklist
- [ ] Type hints present
- [ ] Error handling implemented
- [ ] Tests added/updated
- [ ] Docstrings complete
- [ ] Ruff checks pass
- [ ] mypy checks pass
- [ ] No print statements (use logging)

### Configuration Management (New KISS System)

**⚠️ Config system refactored to unversioned `indexed-config` package**

### Architecture
```python
# Package: indexed-config (unversioned, stable across API versions)
from indexed_config import ConfigService, Provider

# Registration (in package __init__.py)
svc = ConfigService.instance()
svc.register(MyConfigSpec, path="section.subsection")

# Usage
provider = svc.bind()  # Validates all registered specs
config_slice = provider.get(MyConfigSpec)  # Typed access
service = MyService(config_slice)
```

### CLI Commands
```bash
indexed config inspect                    # Show merged config
indexed config set core.v1.indexing.chunk_size 512  # Set values
indexed config delete old.section        # Remove keys
indexed config validate                   # Validate specs
indexed config init                       # Initialize workspace config
```

### Config File Merge Strategy
1. **Defaults** from Pydantic model defaults
2. **Global**: `~/.config/indexed/config.toml`
3. **Workspace**: `./.indexed/config.toml` (overrides global)
4. **Environment**: `INDEXED__section__key=value` (highest priority)

### Config File Structure
```toml
# .indexed/config.toml (workspace) or ~/.config/indexed/config.toml (global)
[core.v1.indexing]
chunk_size = 512
chunk_overlap = 50

[core.v1.embedding] 
provider = "sentence-transformers"
model_name = "all-MiniLM-L6-v2"

[connectors.jira]
url = "https://jira.example.com"
query = "project = PROJ"
```

### Pydantic Config Specs
```python
from pydantic import BaseModel, Field

class CoreV1Indexing(BaseModel):
    chunk_size: int = Field(default=512)
    chunk_overlap: int = Field(default=50)

class JiraConfig(BaseModel):
    url: str = Field(..., description="Jira base URL")
    query: str = Field(..., description="JQL query")
    token: Optional[str] = None

# Registration
ConfigService.instance().register(CoreV1Indexing, path="core.v1.indexing")
ConfigService.instance().register(JiraConfig, path="connectors.jira")
```

### Environment Variables
```bash
# Override any config value via environment
EXPORT INDEXED__core__v1__indexing__chunk_size=1024
EXPORT INDEXED__connectors__jira__url="https://my-jira.com"
```

### Legacy Config (Deprecated)
```python
# ⚠️ DEPRECATED - use ConfigService instead
from core.v1 import Config  # Shows deprecation warning
config = Config.load()      # Legacy API
```

## Performance Guidelines

### Memory Management
- Use generators for large document collections
- Batch processing for embeddings
- Lazy loading of indexes

### Optimization
- Profile before optimizing
- Use numpy for numerical operations
- Leverage FAISS optimizations
- Cache expensive operations

## Security Best Practices

### API Keys
- Store in environment variables or config files (never in code)
- Use `.env` files (excluded from git)
- Validate before use

### Input Validation
- Validate all user inputs with Pydantic
- Sanitize file paths
- Check file permissions

## Documentation Standards

### Code Comments
- Explain WHY, not WHAT
- Document complex logic
- Link to relevant issues/PRs

### README Updates
- Keep installation instructions current
- Document new features
- Update examples

## Legacy Code Handling

**Current State (v1.0):** No legacy implementation remains in the codebase. This section is retained for historical context only.

**Historical Context:**
- During Phase 1 monorepo migration, old code was temporarily in `indexed-core/legacy/`
- Phase 2 completed migration to `core.v1` architecture
- All legacy code has been removed; `core.v1` is the sole implementation

**For Future Reference:**
- If adding new major versions (e.g., `core.v2`), follow similar versioning pattern
- Maintain clear separation between versions if coexistence is needed
- Prefer clean breaks over maintaining multiple implementations

## Migration Notes

### Jira Client Migration (2025-10-16)

**From:** `jira>=3.5.0` (jira-python)
**To:** `atlassian-python-api>=4.0.7`

**Rationale:** Consolidate Atlassian service dependencies to prepare for future Confluence and Bitbucket connectors.

**Key API Changes:**
```python
# OLD (jira-python)
from jira import JIRA
client = JIRA(server=url, basic_auth=(email, token))
result = client.search_issues(jql, startAt=0, maxResults=50, json_result=True)

# NEW (atlassian-python-api)  
from atlassian import Jira
client = Jira(url=url, username=email, password=token, cloud=True)
result = client.jql(jql, start=0, limit=50)
```

**Authentication Differences:**
- **Cloud**: `Jira(url=..., username=email, password=api_token, cloud=True)`
- **Server/DC with Token**: `Jira(url=..., token=pat_token)`
- **Server/DC with Credentials**: `Jira(url=..., username=user, password=pass, cloud=False)`

**Benefits:**
- Single dependency for all Atlassian services
- Consistent API patterns across Jira, Confluence, Bitbucket
- Better support for both Cloud and Server/DC environments
- Future-proofs connector architecture

## Key Principles Summary

1. **KISS** - Keep implementations simple and clear
2. **Type Safety** - Type hints everywhere
3. **Dependency Injection** - No hardcoded dependencies
4. **Configuration-Driven** - Behavior controlled by config
5. **Testability** - All code should be easily testable
6. **Error Handling** - Explicit and informative
7. **Documentation** - Clear docstrings and comments
8. **Use uv** - ALWAYS use `uv run` for commands

---

**Remember:** These are not suggestions - they are requirements for code quality and maintainability.

