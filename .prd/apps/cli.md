# CLI Application (`indexed-cli`)

## Overview

The CLI application is the primary interface for document indexing and searching. It provides essential commands for individual developers who need fast, local document search. Built on the shared core library, it's designed to be extended with a server application in the future.

## Requirements

### Functional Requirements

**FR-CLI-001: Document Indexing (MVP)**
- **MUST** provide `index` command to create document collections
- **MUST** support local files (PDF, TXT, MD, DOCX)
- **MUST** show progress during indexing
- **MUST** handle indexing errors gracefully

**FR-CLI-002: Document Search (MVP)**
- **MUST** provide `search` command for semantic search
- **MUST** return results with relevance scores
- **MUST** support searching specific collections
- **MUST** display results in readable format

**FR-CLI-003: Collection Management (MVP)**
- **MUST** provide `list` command to show collections
- **MUST** provide `delete` command to remove collections
- **MUST** show basic collection information (name, document count)

**FR-CLI-004: Configuration (MVP)**
- **MUST** support basic configuration management
- **MUST** allow setting OpenAI API key
- **MUST** use sensible defaults for all settings

### Non-Functional Requirements

**NFR-CLI-001: Usability (MVP)**
- **MUST** provide clear command help and error messages
- **MUST** use Rich for nice console output (colors, progress bars)
- **MUST** handle Ctrl+C interruption gracefully

**NFR-CLI-002: Performance (MVP)**
- **MUST** start commands quickly (< 2 seconds)
- **MUST** show progress for indexing operations
- **MUST** return search results quickly (< 1 second for typical queries)

## Structure

### Application Layout

```
apps/cli/
├── pyproject.toml              # Package configuration
├── README.md                   # CLI documentation
├── src/
│   └── llamaindex_search_cli/
│       ├── __init__.py         # Package init
│       ├── main.py             # Main CLI entry point  
│       ├── commands/           # Command implementations
│       │   ├── __init__.py
│       │   ├── index.py        # Index command
│       │   ├── search.py       # Search command
│       │   ├── list.py         # List collections
│       │   ├── delete.py       # Delete collection
│       │   └── config.py       # Config commands
│       ├── ui/                 # Rich UI components
│       │   ├── __init__.py
│       │   ├── console.py      # Console utilities
│       │   ├── progress.py     # Progress bars
│       │   └── formatting.py   # Result formatting
│       └── utils/              # CLI utilities
│           ├── __init__.py
│           ├── config.py       # Config loading
│           └── validation.py   # Input validation
└── tests/                      # CLI tests
    ├── __init__.py
    └── test_commands.py
```

### Essential Commands (MVP)

```bash
# Setup and initialization
indexed init                           # Guided setup wizard

# Source management
indexed source add folder --path ./docs --name "project-docs"
indexed source add jira --base-url https://company.atlassian.net --name "tickets"  
indexed source list                    # List configured sources
indexed source show project-docs       # Show source details
indexed source update [name]           # Update all or specific source
indexed source remove project-docs     # Remove source

# Search and status
indexed search "deployment strategies" # Search all sources
indexed search "API docs" --sources project-docs  # Search specific source
indexed status                         # Show all collection status
indexed status --sources project-docs  # Show specific collection status

# MCP integration
indexed mcp                           # Start MCP stdio server
indexed mcp --sources project-docs    # MCP server for specific sources

# Configuration management
indexed config show                   # Show current configuration
indexed config set search.max_docs 20 # Update config value
```

### Future Commands (Phase 2+)

```bash
# Enhanced search
llsearch search "query" --filter type:pdf --limit 20
llsearch similar path/to/document.pdf  # Find similar documents

# Collection management
llsearch update project-docs           # Re-index changed documents
llsearch export project-docs           # Export collection data
```

## Jobs to be Done

### Job 1: Quick Setup and Configuration
**When** a developer first installs the CLI  
**I want** to quickly set up collections and start indexing documents  
**So that** I can begin searching my documents with minimal friction

**Acceptance Criteria**:
- Interactive setup wizard that guides through initial configuration
- Pre-configured templates for common use cases (docs, code, tickets)
- Automatic detection of common document sources (Git repos, local folders)
- Configuration validation with helpful error messages
- Example configurations and best practices documentation

### Job 2: Efficient Document Management
**When** managing document collections over time  
**I want** to easily add, update, and maintain my indexed content  
**So that** my search results stay current and comprehensive

**Acceptance Criteria**:
- Incremental updates that only process changed documents
- Batch operations for managing multiple collections
- Progress tracking for long-running operations
- Dry-run mode to preview changes before execution
- Collection health monitoring and maintenance tools

### Job 3: Powerful Search Interface
**When** searching for information across my documents  
**I want** flexible search options with rich result presentation  
**So that** I can quickly find relevant information in different contexts

**Acceptance Criteria**:
- Interactive search mode with real-time results
- Advanced filtering and query syntax
- Multiple output formats for different use cases
- Search result ranking with relevance explanations
- Search history and saved queries

### Job 4: AI Agent Integration
**When** using AI coding assistants or agents  
**I want** them to access my indexed documents seamlessly  
**So that** they can provide context-aware assistance based on my knowledge base

**Acceptance Criteria**:
- Embedded MCP server that starts automatically
- Comprehensive MCP tools for search and collection management
- Secure authentication for AI agent access
- Performance optimized for AI agent usage patterns
- Easy integration with popular AI development tools

## Technical Implementation

### CLI Framework Design

```python
import typer
from rich.console import Console
from rich.progress import Progress
from typing import Optional, List

app = typer.Typer(
    name="llamaindex-search",
    help="LlamaIndex Search CLI - Document indexing and search",
    add_completion=False,
)

# Global console for rich output
console = Console()

@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    collection: Optional[List[str]] = typer.Option(None, "--collection", "-c"),
    limit: int = typer.Option(10, "--limit", "-l"),
    format: str = typer.Option("table", "--format", "-f"),
    interactive: bool = typer.Option(False, "--interactive", "-i"),
) -> None:
    """Search documents in collections."""
    
    if interactive:
        run_interactive_search()
    else:
        results = perform_search(query, collection, limit)
        display_results(results, format)

def run_interactive_search() -> None:
    """Run interactive search session."""
    console.print("[bold blue]Interactive Search Mode[/bold blue]")
    console.print("Type your queries, use 'help' for commands, 'quit' to exit")
    
    while True:
        query = typer.prompt("Search")
        if query.lower() in ['quit', 'exit', 'q']:
            break
        elif query.lower() == 'help':
            show_interactive_help()
        else:
            results = perform_search(query)
            display_results(results, "table")
```

### Collection Management Implementation

```python
from rich.table import Table
from rich.prompt import Confirm
from llamaindex_search_core import create_collection, SearchEngine

@app.group()
def collections():
    """Manage document collections."""
    pass

@collections.command("create")
def create_collection_cmd(
    name: str = typer.Option(..., "--name", "-n"),
    source: str = typer.Option(..., "--source", "-s"),
    path: Optional[str] = typer.Option(None, "--path", "-p"),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    dry_run: bool = typer.Option(False, "--dry-run", "-d"),
) -> None:
    """Create a new document collection."""
    
    # Load configuration
    config_obj = load_config(config)
    
    # Setup connector based on source type
    connector = setup_connector(source, path, config_obj)
    
    if dry_run:
        console.print("[yellow]Dry run mode - no changes will be made[/yellow]")
        preview_collection_creation(name, connector)
        return
    
    # Create collection with progress tracking
    with Progress() as progress:
        task = progress.add_task("Creating collection...", total=100)
        
        collection = create_collection(
            name=name,
            connector=connector,
            config=config_obj,
            progress_callback=lambda p: progress.update(task, completed=p)
        )
    
    console.print(f"[green]✓ Collection '{name}' created successfully[/green]")
    show_collection_stats(collection)

@collections.command("list")
def list_collections_cmd(
    format: str = typer.Option("table", "--format", "-f"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """List all collections."""
    
    collections_data = get_all_collections()
    
    if format == "table":
        table = Table(title="Document Collections")
        table.add_column("Name", style="cyan")
        table.add_column("Source", style="green") 
        table.add_column("Documents", justify="right")
        table.add_column("Size", justify="right")
        table.add_column("Last Updated")
        
        for collection in collections_data:
            table.add_row(
                collection.name,
                collection.source,
                str(collection.document_count),
                format_size(collection.storage_size),
                collection.last_updated.strftime("%Y-%m-%d %H:%M")
            )
        
        console.print(table)
    elif format == "json":
        console.print_json([c.dict() for c in collections_data])
```

### Interactive Search Implementation

```python
from rich.live import Live
from rich.table import Table
from rich.text import Text
import asyncio

class InteractiveSearchSession:
    """Interactive search session with live results."""
    
    def __init__(self, search_engine: SearchEngine):
        self.search_engine = search_engine
        self.search_history = []
        self.favorites = []
    
    async def run_session(self) -> None:
        """Run interactive search session."""
        console.print("[bold blue]🔍 Interactive Search Mode[/bold blue]")
        console.print("Commands: help, history, favorites, collections, quit")
        console.print("")
        
        while True:
            try:
                query = await self.get_search_input()
                
                if query.lower() in ['quit', 'exit', 'q']:
                    break
                elif query.startswith('/'):
                    await self.handle_command(query[1:])
                else:
                    await self.perform_search(query)
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]Session interrupted[/yellow]")
                break
    
    async def perform_search(self, query: str) -> None:
        """Perform search with live results display."""
        self.search_history.append(query)
        
        # Create live display
        with Live(self.create_search_table(), refresh_per_second=4) as live:
            # Perform search
            results = await self.search_engine.search(
                query=query,
                max_results=20
            )
            
            # Update display with results
            live.update(self.create_results_table(query, results))
            
            # Wait for user to review results
            input("\nPress Enter to continue...")
    
    def create_results_table(self, query: str, results) -> Table:
        """Create results display table."""
        table = Table(title=f"Search Results: {query}")
        table.add_column("Rank", width=4)
        table.add_column("Title", style="bold")
        table.add_column("Source", style="dim")
        table.add_column("Score", justify="right", style="green")
        
        for i, result in enumerate(results.nodes[:10], 1):
            table.add_row(
                str(i),
                result.text[:80] + "..." if len(result.text) > 80 else result.text,
                result.metadata.get('source', 'Unknown'),
                f"{result.score:.3f}"
            )
        
        return table
```

### Local MCP Server Integration

```python
from fastmcp import FastMCP
from llamaindex_search_core import SearchEngine

class LocalMCPServer:
    """Local MCP server for AI agent integration."""
    
    def __init__(self, search_engine: SearchEngine, port: int = 8080):
        self.search_engine = search_engine
        self.mcp = FastMCP("llamaindex-search")
        self.port = port
        self.setup_tools()
    
    def setup_tools(self) -> None:
        """Setup MCP tools for AI agents."""
        
        @self.mcp.tool()
        async def search_documents(
            query: str,
            collection: str = None,
            max_results: int = 10,
            filters: dict = None
        ) -> dict:
            """Search documents using semantic similarity."""
            
            results = await self.search_engine.search(
                query=query,
                collections=[collection] if collection else None,
                filters=filters,
                max_results=max_results
            )
            
            return {
                "query": query,
                "total_results": len(results.nodes),
                "results": [
                    {
                        "text": node.text,
                        "metadata": node.metadata,
                        "score": node.score
                    }
                    for node in results.nodes
                ]
            }
        
        @self.mcp.tool()
        async def list_collections() -> dict:
            """List available document collections."""
            collections = await self.search_engine.get_collections()
            return {
                "collections": [
                    {
                        "name": col.name,
                        "document_count": col.document_count,
                        "last_updated": col.last_updated.isoformat()
                    }
                    for col in collections
                ]
            }
        
        @self.mcp.tool()
        async def create_collection(
            name: str,
            source_type: str,
            source_config: dict
        ) -> dict:
            """Create a new document collection."""
            # Implementation for collection creation via MCP
            pass
    
    async def start_server(self) -> None:
        """Start the MCP server."""
        console.print(f"[green]Starting MCP server on port {self.port}[/green]")
        await self.mcp.run(port=self.port)

# MCP server management commands
@app.group()
def mcp():
    """Manage local MCP server."""
    pass

@mcp.command("start")
def start_mcp_server(
    port: int = typer.Option(8080, "--port", "-p"),
    host: str = typer.Option("localhost", "--host", "-h"),
    daemon: bool = typer.Option(False, "--daemon", "-d"),
) -> None:
    """Start local MCP server."""
    
    search_engine = SearchEngine.from_config()
    server = LocalMCPServer(search_engine, port)
    
    if daemon:
        # Start as daemon process
        start_daemon_server(server, host, port)
    else:
        # Run in foreground
        asyncio.run(server.start_server())
```

### Configuration Management

```python
from pathlib import Path
from pydantic import BaseSettings
import tomli_w
import tomli

class CLIConfig(BaseSettings):
    """CLI-specific configuration."""
    
    # Default paths
    data_dir: Path = Path.home() / ".llamaindex-search"
    config_file: Path = data_dir / "config.toml"
    cache_dir: Path = data_dir / "cache"
    
    # Display preferences
    default_format: str = "table"
    max_results: int = 20
    colors_enabled: bool = True
    
    # MCP server settings
    mcp_port: int = 8080
    mcp_host: str = "localhost"
    mcp_auto_start: bool = False
    
    class Config:
        env_prefix = "LLAMAINDEX_SEARCH_"

@app.group()
def config():
    """Manage CLI configuration."""
    pass

@config.command("init")
def init_config(
    wizard: bool = typer.Option(False, "--wizard", "-w"),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Initialize configuration."""
    
    cli_config = CLIConfig()
    
    if cli_config.config_file.exists() and not force:
        if not Confirm.ask(f"Configuration exists at {cli_config.config_file}. Overwrite?"):
            raise typer.Abort()
    
    if wizard:
        config_data = run_setup_wizard()
    else:
        config_data = get_default_config()
    
    # Create directories
    cli_config.data_dir.mkdir(parents=True, exist_ok=True)
    cli_config.cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Write configuration
    with open(cli_config.config_file, "wb") as f:
        tomli_w.dump(config_data, f)
    
    console.print(f"[green]✓ Configuration saved to {cli_config.config_file}[/green]")

def run_setup_wizard() -> dict:
    """Run interactive setup wizard."""
    console.print("[bold blue]Configuration Setup Wizard[/bold blue]")
    console.print("This wizard will help you set up LlamaIndex Search CLI\n")
    
    # Collect user preferences
    config_data = {}
    
    # Data storage location
    data_dir = typer.prompt(
        "Data directory",
        default=str(Path.home() / ".llamaindex-search")
    )
    config_data["data_dir"] = data_dir
    
    # Default embedding provider
    embedding_provider = typer.prompt(
        "Embedding provider",
        default="openai",
        type=typer.Choice(["openai", "huggingface", "ollama"])
    )
    config_data["embedding"] = {"provider": embedding_provider}
    
    if embedding_provider == "openai":
        api_key = typer.prompt("OpenAI API key", hide_input=True)
        config_data["embedding"]["api_key"] = api_key
    
    # MCP server preferences
    if Confirm.ask("Enable MCP server for AI agent integration?", default=True):
        mcp_port = typer.prompt("MCP server port", default=8080, type=int)
        config_data["mcp"] = {
            "enabled": True,
            "port": mcp_port,
            "auto_start": Confirm.ask("Auto-start MCP server?", default=False)
        }
    
    return config_data
```

## Integration Points

### Core Package Integration

The CLI package integrates tightly with the core package:

- **Search Engine**: Direct usage of `SearchEngine` class for all search operations
- **Collection Management**: Uses core collection creation and management APIs
- **Configuration**: Extends core configuration with CLI-specific settings
- **Async Operations**: Leverages core async capabilities for responsive CLI experience

### MCP Integration

The CLI provides a local MCP server that exposes core functionality:

- **Search Tools**: Direct access to document search capabilities
- **Collection Tools**: Management of document collections
- **Resource Access**: Access to collection metadata and statistics
- **Local Storage**: Efficient local storage for CLI-specific data

### Rich Console Integration

Extensive use of Rich library for enhanced user experience:

- **Progress Tracking**: Visual progress bars for long-running operations
- **Tables**: Formatted display of search results and collection data
- **Colors and Styling**: Consistent visual hierarchy and emphasis
- **Interactive Elements**: Prompts, confirmations, and live updates

## Testing Strategy

### Unit Tests
- Individual command functionality
- Configuration loading and validation
- Output formatting and display
- MCP tool implementations

### Integration Tests
- End-to-end CLI workflows
- MCP server functionality
- Configuration wizard
- Search result formatting

### User Experience Tests
- Command completion and help text
- Error message clarity
- Progress indication accuracy
- Interactive mode usability

## Dependencies

```toml
dependencies = [
    "indexed-core>=1.0.0",
    "typer[all]>=0.9.0",
    "rich>=13.0.0",
    "questionary>=2.0.0",
    "fastmcp>=0.3.0",
    "tomli>=2.0.0",
    "tomli-w>=1.0.0",
    "click-completion>=0.5.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-typer>=0.0.3",
]

[project.scripts]
indexed = "indexed_cli:app"
```

The CLI component provides a powerful, user-friendly interface that makes the core search functionality accessible to developers and power users while enabling AI agent integration through the embedded MCP server.