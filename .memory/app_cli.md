# CLI Application (indexed-cli)

## Overview

The CLI application is the primary user interface for the Indexed document search system. It provides essential commands for document indexing, searching, and collection management.

**Location:** `apps/indexed-cli/`  
**Entry Points:** 
- `indexed-cli` - Main CLI application
- `indexed-mcp` - MCP server for AI agent integration

## Architecture

### Application Structure

```
apps/indexed-cli/
├── src/indexed_cli/
│   ├── __init__.py
│   ├── app.py              # Main Typer application
│   ├── commands/           # Command implementations
│   │   ├── __init__.py
│   │   ├── create.py      # Collection creation
│   │   ├── search.py      # Search commands
│   │   ├── update.py      # Update collections
│   │   ├── delete.py      # Delete collections
│   │   ├── index.py       # Index management
│   │   └── legacy.py      # Legacy command wrappers
│   ├── engines/           # Engine selection logic
│   │   ├── __init__.py
│   │   ├── base.py        # Base engine interface
│   │   ├── legacy_engine.py  # Legacy implementation
│   │   └── v2_engine.py   # New implementation
│   └── server/
│       ├── __init__.py
│       └── mcp.py         # FastMCP server
├── pyproject.toml
└── README.md
```

## Essential Commands (Current Implementation)

### Collection Management

**Create Collection:**
```bash
# From local files
indexed-cli create files -c my-docs --basePath ./documents

# From Jira (legacy)
indexed-cli create jira -c tickets --baseUrl https://company.atlassian.net --jql "project = PROJ"

# From Confluence (legacy)
indexed-cli create confluence -c wiki --baseUrl https://company.atlassian.net --cql "space = DEV"
```

**Update Collection:**
```bash
indexed-cli update              # Update all collections
indexed-cli update -c my-docs   # Update specific collection
```

**Delete Collection:**
```bash
indexed-cli delete -c my-docs --yes
```

### Search Operations

**Basic Search:**
```bash
indexed-cli search "authentication methods"
indexed-cli search "API docs" -c my-docs
indexed-cli search "query" --json --maxNumberOfDocuments 5
```

### Inspection & Status

**Inspect Collections:**
```bash
indexed-cli inspect                           # List all collections
indexed-cli inspect --json                    # JSON output
indexed-cli inspect --include-index-size      # Include size info
```

**List Collections:**
```bash
indexed-cli list    # List all collections
```

### MCP Server

**Start MCP Server:**
```bash
indexed-mcp         # Start MCP stdio server for AI agents
```

## Command Implementation Pattern

### Basic Command Structure

```python
import typer
from typing import Optional
from indexed_core.legacy.services import CollectionService

app = typer.Typer()

@app.command()
def create_files(
    collection_name: str = typer.Option(..., "--collection-name", "-c"),
    base_path: str = typer.Option(..., "--basePath"),
    include_patterns: Optional[str] = typer.Option(None, "--includePatterns"),
    exclude_patterns: Optional[str] = typer.Option(None, "--excludePatterns")
) -> None:
    """Create a collection from local files."""
    
    # 1. Load configuration
    config = load_config()
    
    # 2. Select engine (legacy vs v2)
    engine = select_engine(config)
    
    # 3. Execute command through engine
    result = engine.create_files_collection(
        collection_name=collection_name,
        base_path=base_path,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns
    )
    
    # 4. Display results
    display_results(result)
```

## Engine Selection Logic

### Two-Engine Architecture

**Purpose:** Support both legacy and new implementations during migration

**Engine Types:**

**1. Legacy Engine** (`engines/legacy_engine.py`)
- Uses existing factory/adapter pattern
- Supports Jira, Confluence, Files connectors
- Mature, battle-tested implementation
- Complex abstractions

**2. V2 Engine** (`engines/v2_engine.py`)
- Uses new controller/service architecture
- Clean dependency injection
- Easier to test and extend
- Supports new features (cloud embeddings, etc.)

**Selection Logic:**
```python
def select_engine(config):
    """Select which engine to use based on config or feature flags."""
    if config.get("use_v2_engine", False):
        return V2Engine(config)
    else:
        return LegacyEngine(config)
```

## MCP Server Integration

### FastMCP Server

**File:** `server/mcp.py`

**Purpose:** Expose document search capabilities to AI agents

**Tools Provided:**

1. **search_collections** - Search across document collections
2. **list_collections** - List available collections
3. **get_collection_info** - Get detailed collection information
4. **create_collection** - Create new collections (future)

**Server Implementation:**
```python
from fastmcp import FastMCP
from indexed_core.legacy.services import CollectionService, SearchService

mcp = FastMCP("indexed-search")

@mcp.tool()
async def search_collections(
    query: str,
    sources: list[str] = None,
    max_results: int = 10
) -> dict:
    """Search for documents across collections."""
    search_service = SearchService()
    results = search_service.search(
        query=query,
        sources=sources,
        max_results=max_results
    )
    return format_search_results(results)

@mcp.tool()
async def list_collections() -> dict:
    """List all available collections."""
    collection_service = CollectionService()
    collections = collection_service.list_collections()
    return {"collections": collections}
```

**Usage:**
```bash
# Start MCP server (stdio mode for Cursor/Claude)
indexed-mcp

# In Cursor/Claude, the server exposes tools like:
# - search_collections
# - list_collections
# - get_collection_info
```

## Configuration Management

### Config Loading

**Priority Order (highest to lowest):**
1. Command-line arguments
2. Environment variables (`INDEXED__*`)
3. Workspace config (`./config.toml`)
4. Global config (`~/.config/indexed/config.toml`)
5. Default values

**Example Config:**
```toml
# config.toml
[paths]
collections_dir = "./data/collections"
cache_dir = "./data/caches"

[search]
max_docs = 10
max_chunks = 30
include_full_text = false

[mcp]
default_sources = ["my-docs", "wiki"]
tool_prefix = "indexed_"

[index]
default_indexer = "FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"
```

## User Experience Patterns

### Output Formatting

**Success Messages:**
```
✅ Collection 'my-docs' created successfully
📊 Indexed 150 documents, 1,234 chunks
```

**Error Messages:**
```
❌ Error: Collection 'my-docs' already exists
💡 Use --force to overwrite or choose a different name
```

**Progress Indicators:**
```
Indexing documents... ━━━━━━━━━━━━━━━━━━━━━━━━ 100% (150/150)
Generating embeddings... ━━━━━━━━━━━━━━━━━━━━━ 85% (1,047/1,234)
```

### JSON Output Mode

All commands support `--json` flag for programmatic use:

```bash
indexed-cli search "query" --json
```

Output:
```json
{
  "query": "query",
  "results": [
    {
      "document_id": "doc-123",
      "content": "...",
      "score": 0.89,
      "metadata": {...}
    }
  ],
  "total_results": 10,
  "execution_time_ms": 145
}
```

## Error Handling

### Command-Level Error Handling

```python
@app.command()
def search(query: str, collection: Optional[str] = None):
    try:
        # Execute search
        results = perform_search(query, collection)
        display_results(results)
    except CollectionNotFoundError as e:
        typer.echo(f"❌ Error: Collection not found: {e.collection_name}")
        typer.echo("💡 Run 'indexed-cli list' to see available collections")
        raise typer.Exit(1)
    except SearchError as e:
        typer.echo(f"❌ Search failed: {e}")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}")
        if debug_mode:
            import traceback
            traceback.print_exc()
        raise typer.Exit(1)
```

## Testing Strategy

### Command Testing

**Test Structure:**
```python
from typer.testing import CliRunner
from indexed_cli.app import app

runner = CliRunner()

def test_create_files_collection():
    result = runner.invoke(app, [
        "create", "files",
        "-c", "test-collection",
        "--basePath", "./test-docs"
    ])
    assert result.exit_code == 0
    assert "created successfully" in result.output

def test_search_command():
    result = runner.invoke(app, [
        "search", "test query",
        "-c", "test-collection"
    ])
    assert result.exit_code == 0
    assert "results" in result.output.lower()
```

### Integration Testing

Test full workflows:
```python
def test_full_workflow():
    # 1. Create collection
    runner.invoke(app, ["create", "files", "-c", "test", "--basePath", "./docs"])
    
    # 2. Search collection
    result = runner.invoke(app, ["search", "query", "-c", "test"])
    assert "results" in result.output
    
    # 3. Delete collection
    runner.invoke(app, ["delete", "-c", "test", "--yes"])
```

## Future Enhancements (Phase 3+)

### Planned CLI Improvements

**Rich UI Components:**
- Interactive progress bars with detailed status
- Formatted tables for search results
- Color-coded output with syntax highlighting
- Interactive collection browser

**Advanced Commands:**
```bash
# Interactive search mode
indexed-cli search --interactive

# Collection health check
indexed-cli doctor -c my-docs

# Export/import collections
indexed-cli export -c my-docs --output backup.tar.gz
indexed-cli import --input backup.tar.gz

# Configuration wizard
indexed-cli init --wizard
```

**Enhanced Search:**
```bash
# Filter by metadata
indexed-cli search "query" --filter type:pdf --filter date:2024

# Similar document search
indexed-cli similar ./path/to/document.pdf

# Search history
indexed-cli history
indexed-cli history --replay 5
```

## Dependencies

**Direct Dependencies:**
```toml
dependencies = [
    "typer>=0.12.3",          # CLI framework
    "mcp>=1.13.0",            # MCP protocol
    "fastmcp>=2.11.3",        # MCP server
    "indexed-core",           # Core library (workspace)
]
```

**Optional Dependencies:**
```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.4.1",
    "pytest-typer>=0.0.3",
]
```

## Key Design Principles

1. **Simple Commands**: Intuitive command names and flags
2. **Helpful Output**: Clear success/error messages with suggestions
3. **JSON Support**: All commands support machine-readable output
4. **Error Recovery**: Graceful error handling with helpful guidance
5. **Progressive Enhancement**: Start simple, add rich UI features later
6. **MCP Integration**: First-class support for AI agent workflows

## Command Reference Quick Guide

| Command | Purpose | Example |
|---------|---------|---------|
| `create files` | Index local files | `indexed-cli create files -c docs --basePath ./` |
| `create jira` | Index Jira issues | `indexed-cli create jira -c tickets --baseUrl ... --jql "..."` |
| `create confluence` | Index Confluence pages | `indexed-cli create confluence -c wiki --baseUrl ... --cql "..."` |
| `search` | Search collections | `indexed-cli search "query" -c docs` |
| `update` | Update collections | `indexed-cli update -c docs` |
| `delete` | Delete collection | `indexed-cli delete -c docs --yes` |
| `inspect` | List collections | `indexed-cli inspect --json` |
| `list` | List collections | `indexed-cli list` |
| `indexed-mcp` | Start MCP server | `indexed-mcp` |

---

This CLI application provides a clean, user-friendly interface to the core document search functionality while maintaining flexibility for future enhancements.
