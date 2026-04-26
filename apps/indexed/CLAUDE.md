# CLI & MCP Server Implementation Guide

This package contains the main user-facing CLI application and the FastMCP server for AI agent integration.

## Package Overview

**Location:** `apps/indexed/`

**Purpose:**
- Command-line interface for all indexing and search operations
- Model Context Protocol server for AI agent integration
- Rich terminal UI components and logging
- Entry points: `indexed` (CLI) and `indexed-mcp` (MCP server)

**Key Files:**
```
src/indexed/
├── app.py                          # Main Typer CLI application (9.3 KB)
├── knowledge/
│   └── commands/
│       ├── create.py               # Collection creation (24.9 KB)
│       ├── search.py               # Semantic search (15.5 KB)
│       ├── update.py               # Collection updates (15.7 KB)
│       ├── inspect.py              # Collection inspection (10.4 KB)
│       └── remove.py               # Collection removal (5.6 KB)
├── config/
│   └── cli.py                      # Configuration CLI commands
├── mcp/
│   ├── cli.py                      # MCP server entry point
│   └── server.py                   # FastMCP server (33.5 KB)
└── utils/
    ├── banner.py                   # ASCII banner & theming
    ├── logging.py                  # Logging setup
    ├── components.py               # Rich UI components
    └── credentials.py              # Credential input helpers
```

## Architecture

### CLI Layer Structure

```
Typer App (app.py)
├── Global callbacks
│   ├── --verbose / --quiet
│   ├── --storage-mode (global|local)
│   └── --config-file
├── Command Groups
│   ├── index
│   │   ├── create       (create new collections)
│   │   ├── search       (semantic search)
│   │   ├── update       (update collections)
│   │   ├── remove       (delete collections)
│   │   └── inspect      (view collection status)
│   ├── config
│   │   ├── inspect      (view configuration)
│   │   ├── set          (update config values)
│   │   ├── validate     (validate configuration)
│   │   └── delete       (remove config keys)
│   └── mcp
│       ├── run          (start MCP server)
│       ├── dev          (MCP with inspector)
│       └── inspect      (view MCP tools)
└── Info Commands
    ├── docs             (open documentation)
    └── license          (display license)
```

### MCP Server Architecture

```
FastMCP Server (server.py)
├── Tools
│   ├── search(query, collection)
│   ├── list_collections()
│   └── collection_status(name)
├── Transport Layer
│   ├── stdio (default, Claude Desktop)
│   ├── http (HTTP server)
│   └── sse (Server-Sent Events)
└── Logging & Error Handling
    ├── Structured JSON logging
    ├── Rich error messages
    └── Debug mode support
```

## Key Commands

### Index Management

**Create a new collection:**
```bash
uv run indexed index create my-collection \
  --source files \
  --source-path ./documents
```

Supported sources: `files`, `jira`, `jiraCloud`, `confluence`, `confluenceCloud`

**Search collections:**
```bash
uv run indexed index search "how to deploy" \
  --collection my-collection \
  --max-results 10
```

**Update a collection:**
```bash
uv run indexed index update my-collection
```

**Inspect collection status:**
```bash
uv run indexed index inspect my-collection
```

**Remove a collection:**
```bash
uv run indexed index remove my-collection
```

### Configuration Management

**View configuration:**
```bash
uv run indexed config inspect
```

**Update configuration:**
```bash
uv run indexed config set core.v1.search.max_docs 20
```

**Validate configuration:**
```bash
uv run indexed config validate
```

### MCP Server

**Start MCP server (stdio, for Claude Desktop):**
```bash
uv run indexed-mcp run
# or: uv run indexed mcp run
```

**Start HTTP server:**
```bash
uv run indexed mcp run --transport http --host 127.0.0.1 --port 8000
```

**Development mode with inspector:**
```bash
uv run indexed mcp dev
```

**View MCP server capabilities (tools, resources, prompts):**
```bash
uv run indexed mcp inspect
```

**Native fastmcp CLI (declarative via `fastmcp.json` at repo root):**
```bash
uv run fastmcp run                       # auto-detects fastmcp.json
uv run fastmcp dev inspector             # MCP Inspector
uv run fastmcp install claude-desktop    # one-shot Claude Desktop install
uv run fastmcp install cursor            # Cursor install
uv run fastmcp inspect                   # JSON capability report
```

`indexed mcp run` and `fastmcp run` resolve to the same server (`fastmcp_server.py` at the repo root re-exports the package server). Prefer `indexed mcp run` for end users; `fastmcp install <client>` is the simplest path for setting up Claude Desktop / Cursor / Claude Code.

## Command Implementation Patterns

### Creating New Commands

All commands follow a consistent pattern:

```python
# commands/my_command.py
from typing import TYPE_CHECKING
import typer
from rich import print

if TYPE_CHECKING:
    from core.v1 import Index

def my_command(
    name: str = typer.Argument(..., help="Resource name"),
    verbose: bool = typer.Option(False, help="Verbose output"),
) -> None:
    """Command description for help text."""
    from . import my_command as this_module

    # Lazy-load heavy dependencies
    index = this_module.index

    try:
        result = index.do_something(name)
        print(f"[green]✓[/green] {result}")
    except Exception as e:
        print(f"[red]✗ Error:[/red] {e}")
        raise typer.Exit(1)

def __getattr__(name: str):
    """Lazy load heavy dependencies for performance and testability."""
    if name == "index":
        from core.v1 import Index
        return Index()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```

**Key Patterns:**
- Use `TYPE_CHECKING` for type hints to avoid runtime imports
- Implement `__getattr__` for lazy loading heavy dependencies
- Access via module (`this_module.attr`) for testability
- Use Rich for formatting (`[green]✓[/green]` for colors)
- Raise `typer.Exit(1)` for error codes

### Testing Commands

Commands are tested with mocked services:

```python
from unittest.mock import patch
from typer.testing import CliRunner
from indexed.app import app

runner = CliRunner()

@patch("indexed.knowledge.commands.my_command.index")
def test_my_command(mock_index):
    mock_index.do_something.return_value = "success"

    result = runner.invoke(app, ["index", "my-command", "test"])

    assert result.exit_code == 0
    assert "✓" in result.stdout
    mock_index.do_something.assert_called_once_with("test")
```

## UI Components

Rich-based terminal components for consistent UI:

### Progress Indicators

```python
from rich.progress import Progress, SpinnerColumn, TextColumn

with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
) as progress:
    task = progress.add_task("Creating collection...", total=None)
    # do work
    progress.update(task, completed=True)
```

### Tables

```python
from rich.table import Table

table = Table(title="Collections")
table.add_column("Name", style="cyan")
table.add_column("Size", style="magenta")
table.add_row("my-docs", "1,234 documents")
print(table)
```

### Panels

```python
from rich.panel import Panel

panel = Panel(
    "Collection created successfully",
    title="Success",
    style="green",
)
print(panel)
```

### Error Display

```python
from rich.console import Console

console = Console()
console.print_exception()  # Full traceback with syntax highlighting
```

## Logging Strategy

Logging is configured per command execution:

```python
# utils/logging.py
from loguru import logger

def setup_logging(verbose: bool = False, log_file: str | None = None):
    """Configure Loguru for command execution."""
    level = "DEBUG" if verbose else "INFO"
    logger.enable("indexed")  # Enable logs from indexed package
    # Add handlers, set level, etc.
```

**Usage in commands:**
```python
def my_command(verbose: bool = False):
    from .utils.logging import setup_logging
    setup_logging(verbose=verbose)

    logger.debug("Starting command")
    # command logic
    logger.info("Command completed")
```

**Logging Levels:**
- `DEBUG` - Detailed diagnostic info, only in verbose mode
- `INFO` - General informational messages
- `WARNING` - Warning messages (config issues, etc.)
- `ERROR` - Error conditions that don't stop execution
- `CRITICAL` - Fatal errors that stop execution

## MCP Server Implementation

The FastMCP server exposes indexed collections to AI agents:

### Tool Implementation

```python
# mcp/server.py
from fastmcp import FastMCP
from core.v1 import Index

mcp = FastMCP("indexed")
index = Index()

@mcp.tool()
def search(query: str, collection: str | None = None) -> dict:
    """Search indexed collections for relevant documents.

    Args:
        query: Natural language search query
        collection: Optional collection name (searches all if not specified)

    Returns:
        Dictionary with results and metadata
    """
    results = index.search(query, collection)
    return {
        "query": query,
        "results": [
            {
                "document": chunk.text,
                "score": chunk.score,
                "source": chunk.source,
                "collection": chunk.collection,
            }
            for chunk in results
        ],
    }

@mcp.tool()
def list_collections() -> dict:
    """List all available collections."""
    collections = index.list_collections()
    return {
        "collections": [
            {
                "name": c.name,
                "document_count": c.document_count,
                "created_at": c.created_at,
            }
            for c in collections
        ],
    }

@mcp.tool()
def collection_status(name: str) -> dict:
    """Get detailed status of a collection."""
    status = index.get_status(name)
    return {
        "name": status.name,
        "document_count": status.document_count,
        "chunk_count": status.chunk_count,
        "embedding_model": status.embedding_model,
        "created_at": status.created_at,
        "last_updated": status.last_updated,
    }
```

### Running the MCP Server

**Claude Desktop Integration (manual config):**
```json
{
  "mcpServers": {
    "indexed": {
      "command": "uv",
      "args": ["run", "indexed-mcp", "run"],
      "env": {
        "INDEXED__storage__mode": "local"
      }
    }
  }
}
```

**Claude Desktop Integration (auto via fastmcp.json):**
```bash
uv run fastmcp install claude-desktop
```
Same trick works for `cursor`, `claude-code`, `gemini-cli`, `goose`, and `mcp-json`.

**HTTP Server:**
```bash
uv run indexed-mcp run --transport http --host 127.0.0.1 --port 8000
```

Then access via:
```bash
curl -X POST http://localhost:8000/call_tool \
  -H "Content-Type: application/json" \
  -d '{"name": "search", "arguments": {"query": "deployment guide"}}'
```

## Performance Optimization

This package uses aggressive lazy loading to achieve sub-second CLI startup:

**Key Techniques:**

1. **Lazy Import Heavy Dependencies**
   - ML libraries (torch, transformers) imported only in commands
   - Use `TYPE_CHECKING` for type hints
   - Implement `__getattr__` for module-level lazy loading

2. **Defer Service Initialization**
   - ConfigService initialized per-command, not in app callback
   - Index facade created only when needed

3. **Minimize Module-Level Imports**
   - No heavy dependencies at package level
   - Use string annotations for forward references

**Result:** CLI help completes in <0.5s despite ML dependencies.

For detailed optimization strategies, see `.cursor/rules/tech/performance-optimization.mdc`.

## Testing

### Running CLI Tests

```bash
# Run all CLI tests
uv run pytest tests/unit/indexed/ -q

# Run specific test file
uv run pytest tests/unit/indexed/test_create_command.py -v

# Run with coverage
uv run pytest tests/unit/indexed/ -q --cov=indexed
```

### Test Fixtures

Shared fixtures for CLI testing:

```python
# tests/conftest.py
import pytest
from typer.testing import CliRunner
from indexed.app import app

@pytest.fixture
def cli_runner():
    return CliRunner()

@pytest.fixture
def mock_index(mocker):
    return mocker.patch("indexed.knowledge.commands.create.index")
```

### Mocking Pattern

Commands are tested by mocking the Index service:

```python
def test_create_command(cli_runner, mock_index):
    mock_index.create_collection.return_value = "collection_created"

    result = cli_runner.invoke(app, [
        "index", "create", "my-collection",
        "--source", "files",
        "--source-path", "/tmp/docs"
    ])

    assert result.exit_code == 0
    mock_index.create_collection.assert_called_once()
```

## Error Handling

Commands follow consistent error handling patterns:

```python
def my_command(name: str) -> None:
    """Command with error handling."""
    try:
        result = index.operation(name)
        print(f"[green]✓[/green] Success: {result}")
    except IndexNotFoundError as e:
        print(f"[red]✗ Collection not found:[/red] {name}")
        raise typer.Exit(1)
    except ValueError as e:
        print(f"[red]✗ Invalid argument:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        print(f"[red]✗ Unexpected error:[/red] {e}")
        logger.exception("Command failed")
        raise typer.Exit(2)
```

## Configuration Integration

Commands access configuration through ConfigService:

```python
from indexed_config import ConfigService

def my_command() -> None:
    config = ConfigService.instance()

    # Access nested config values
    max_results = config.get("app.search.max_docs")

    # Get typed config
    search_config = config.get("core.v1.search")

    # Override via CLI arg (if needed)
    search_config.max_docs = 20
```

## Entry Points

### CLI Entry Point

**File:** `src/indexed/app.py`

```python
def main():
    """Main CLI entry point."""
    app()

if __name__ == "__main__":
    main()
```

**Configured in pyproject.toml:**
```toml
[project.scripts]
indexed = "indexed.app:main"
```

### MCP Entry Point

**File:** `src/indexed/mcp/cli.py`

```python
def cli_main():
    """MCP server entry point."""
    # Parse args (stdio, http, sse)
    # Run FastMCP server
    pass
```

**Configured in pyproject.toml:**
```toml
[project.scripts]
indexed-mcp = "indexed.mcp.cli:cli_main"
```

## Common Patterns

### Pattern 1: Command with Collection Selection

```python
@app.command()
def search(
    query: str = typer.Argument(...),
    collection: str | None = typer.Option(None, help="Collection name"),
    max_results: int = typer.Option(10),
) -> None:
    """Search indexed collections."""
    from . import search as this_module
    index = this_module.index

    results = index.search(query, collection, max_results=max_results)
    # display results
```

### Pattern 2: Command with Progress

```python
@app.command()
def create(name: str) -> None:
    """Create a new collection."""
    from . import create as this_module
    from rich.progress import track

    index = this_module.index

    for step in track(range(100), description="Creating collection..."):
        # do work
        pass
```

### Pattern 3: Command with Credentials

```python
@app.command()
def create_jira(name: str) -> None:
    """Create collection from Jira."""
    from . import create_jira as this_module
    from .utils.credentials import prompt_for_credentials

    index = this_module.index

    creds = prompt_for_credentials("Jira", ["url", "email", "api_token"])
    index.create_from_jira(name, **creds)
```

## Related Documentation

- **[Root CURSOR.md](../../CURSOR.md)** - Project overview
- **[indexed-core CURSOR.md](../../packages/indexed-core/CURSOR.md)** - Engine architecture
- **[Configuration CURSOR.md](../../packages/indexed-config/CURSOR.md)** - Config system
- **[.cursor/rules/tech/performance-optimization.mdc](.../../.cursor/rules/tech/performance-optimization.mdc)** - CLI optimization

---

**Last Updated:** January 24, 2026
