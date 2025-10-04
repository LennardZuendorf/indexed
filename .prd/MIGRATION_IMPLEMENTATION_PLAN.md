# Migration & Rewrite Implementation Plan

Based on analysis of the current codebase and PRD requirements, here's the comprehensive plan to migrate to a monorepo structure with LlamaIndex core and improved CLI.

## 🔍 Current State Analysis

### Current Architecture Issues
1. **Mixed Concerns**: CLI, commands, and core logic are intermixed in `src/`
2. **Legacy Implementation**: Custom vector search instead of LlamaIndex
3. **Complex Abstractions**: Factory patterns and adapters for simple operations
4. **Basic CLI UX**: Plain text output, no rich formatting or progress indicators
5. **Monolithic Configuration**: Single pyproject.toml for entire application
6. **Custom Indexing**: FAISS + SentenceTransformers with custom storage format

### Current Working Features (To Preserve)
1. **Command Structure**: `indexed source add folder`, `indexed search`, `indexed inspect`
2. **Multi-source Support**: Jira, Confluence, local files
3. **FAISS Vector Storage**: Works but needs modernization
4. **Configuration Management**: TOML-based configuration
5. **MCP Integration**: Basic MCP server functionality

## 🚀 Implementation Plan - 3 Major Phases

### Phase 1: Monorepo Migration (Foundation)
**Duration**: 1-2 weeks  
**Goal**: Restructure codebase into proper monorepo without changing functionality

#### 1.1 Create Monorepo Structure
```bash
# Execute the uv monorepo setup from uv-monorepo-guide.md
mkdir -p packages/{indexed-core,indexed-cli}
cd packages/indexed-core && uv init --lib indexed-core
cd ../indexed-cli && uv init indexed-cli
```

#### 1.2 Move and Organize Code
**Core Library** (`packages/indexed-core/src/indexed_core/`):
```
📦 indexed-core/
├── pyproject.toml               # Core library dependencies
└── src/indexed_core/
    ├── __init__.py             # Public API exports
    ├── legacy/                 # Current implementation (temporary)
    │   ├── core/              # From src/main/core/
    │   ├── services/          # From src/main/services/
    │   ├── sources/           # From src/main/sources/
    │   ├── indexes/           # From src/main/indexes/
    │   ├── persisters/        # From src/main/persisters/
    │   ├── factories/         # From src/main/factories/
    │   └── utils/             # From src/main/utils/
    ├── config/                 # Configuration management (keep current)
    └── models/                 # Pydantic models (from services/models.py)
```

**CLI Application** (`packages/indexed-cli/src/indexed_cli/`):
```
📦 indexed-cli/
├── pyproject.toml              # CLI + MCP dependencies
└── src/indexed_cli/
    ├── __init__.py
    ├── app.py                  # From src/cli/app.py (updated imports)
    ├── commands/               # From src/commands/ (updated imports)
    ├── mcp.py                  # From src/server/mcp.py
    └── config/                 # From src/config/ (CLI-specific config)
```

#### 1.3 Update Import Paths
**Systematic import updates**:
- CLI: `from main.services import` → `from indexed_core.legacy.services import`
- Commands: `from main.core import` → `from indexed_core.legacy.core import`
- Internal: Keep relative imports within each package

#### 1.4 Update Configuration Files
**Root workspace `pyproject.toml`** (following uv-monorepo-guide.md)
**Package-specific pyproject.toml files** with correct dependencies

#### 1.5 Test Migration
```bash
# Test the migration worked
uv sync
cd packages/indexed-cli
uv run indexed-cli --help
uv run indexed-cli inspect
```

### Phase 2: Core Library Rewrite (LlamaIndex Migration)
**Duration**: 3-4 weeks  
**Goal**: Replace custom implementation with LlamaIndex + FAISS + HuggingFace

#### 2.1 New Core Architecture
Create new implementation alongside legacy code in `packages/indexed-core/`:

```
📦 indexed-core/src/indexed_core/
├── legacy/                     # Keep old code during transition
├── llamaindex/                 # NEW: LlamaIndex implementation
│   ├── __init__.py
│   ├── engine.py              # Main SearchEngine class
│   ├── storage.py             # FAISS + LlamaIndex storage
│   ├── embeddings.py          # HuggingFace embeddings wrapper
│   ├── ingestion.py           # Document processing pipeline
│   └── connectors/            # Source connectors (files, jira, confluence)
├── config/                     # Enhanced configuration
└── models/                     # Enhanced data models
```

#### 2.2 Core SearchEngine Implementation
**Primary class**: `indexed_core.llamaindex.engine.SearchEngine`

```python
# packages/indexed-core/src/indexed_core/llamaindex/engine.py

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.vector_stores.faiss import FaissVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import faiss
from pathlib import Path

class SearchEngine:
    """LlamaIndex-powered search engine."""
    
    def __init__(self, collection_name: str, storage_dir: Path):
        self.collection_name = collection_name
        self.storage_dir = storage_dir
        
        # HuggingFace embeddings (local, no API key needed)
        self.embed_model = HuggingFaceEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        # FAISS vector store
        self._setup_vector_store()
        
    def _setup_vector_store(self):
        """Initialize or load FAISS vector store."""
        vector_store_path = self.storage_dir / "vector_store"
        
        if vector_store_path.exists():
            # Load existing
            self.vector_store = FaissVectorStore.from_persist_dir(
                persist_dir=str(vector_store_path)
            )
        else:
            # Create new
            faiss_index = faiss.IndexFlatL2(384)  # MiniLM dimension
            self.vector_store = FaissVectorStore(faiss_index=faiss_index)
    
    def index_documents(self, documents) -> None:
        """Index documents using LlamaIndex pipeline."""
        storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )
        
        self.index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            embed_model=self.embed_model
        )
        
        # Persist to disk
        self.index.storage_context.persist(
            persist_dir=str(self.storage_dir)
        )
    
    def search(self, query: str, top_k: int = 10):
        """Search using LlamaIndex query engine."""
        query_engine = self.index.as_query_engine(
            similarity_top_k=top_k
        )
        response = query_engine.query(query)
        return response
```

#### 2.3 Document Connector Refactoring
**Goal**: Simplify current complex factory/adapter pattern

```python
# packages/indexed-core/src/indexed_core/llamaindex/connectors/base.py

from abc import ABC, abstractmethod
from llama_index.core import Document
from typing import List

class DocumentConnector(ABC):
    """Base connector for document sources."""
    
    @abstractmethod
    def load_documents(self) -> List[Document]:
        """Load documents and return LlamaIndex Document objects."""
        pass

# packages/indexed-core/src/indexed_core/llamaindex/connectors/files.py
class FilesConnector(DocumentConnector):
    def __init__(self, base_path: str, patterns: List[str] = None):
        self.base_path = Path(base_path)
        self.patterns = patterns or ["**/*.txt", "**/*.md", "**/*.pdf"]
    
    def load_documents(self) -> List[Document]:
        """Load files using LlamaIndex SimpleDirectoryReader."""
        from llama_index.core import SimpleDirectoryReader
        
        reader = SimpleDirectoryReader(
            input_dir=str(self.base_path),
            required_exts=[".txt", ".md", ".pdf", ".docx"]
        )
        return reader.load_data()
```

#### 2.4 Configuration Enhancement
**New configuration structure** (maintaining backward compatibility):

```python
# packages/indexed-core/src/indexed_core/config/settings.py

from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Dict, List, Optional

class IndexedSettings(BaseSettings):
    """Enhanced settings with LlamaIndex support."""
    
    # Data directories
    data_dir: Path = Path("./data")
    collections_dir: Path = data_dir / "collections"
    cache_dir: Path = data_dir / "cache"
    
    # Embedding model settings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_device: str = "cpu"
    
    # Search settings
    default_top_k: int = 10
    max_chunks_per_doc: int = 30
    chunk_size: int = 512
    chunk_overlap: int = 50
    
    # Legacy compatibility
    sources: Dict = {}  # Keep existing source configs
    
    class Config:
        env_prefix = "INDEXED_"
        env_file = ".env"
```

#### 2.5 Gradual Migration Strategy
1. **Implement alongside legacy**: New code in `llamaindex/` module
2. **Feature flags**: Allow switching between legacy and new implementation
3. **CLI compatibility**: Same commands, different backend
4. **Data migration**: Tool to convert legacy FAISS indexes to LlamaIndex format

```python
# Migration command in CLI
@app.command("migrate")
def migrate_to_llamaindex():
    """Migrate legacy collections to LlamaIndex format."""
    # Implementation to convert old storage format
```

### Phase 3: Enhanced CLI (Rich UX)
**Duration**: 2-3 weeks  
**Goal**: Modern CLI experience with rich output, progress bars, and better configuration

#### 3.1 Enhanced CLI Architecture
```
📦 indexed-cli/src/indexed_cli/
├── app.py                      # Enhanced Typer app
├── ui/                         # Rich UI components
│   ├── progress.py            # Progress bars for indexing
│   ├── tables.py              # Rich tables for results
│   ├── prompts.py             # Interactive configuration
│   ├── themes.py              # Color schemes
│   └── console.py             # Centralized console management
├── commands/                   # Enhanced commands
│   ├── init.py                # Interactive setup wizard
│   ├── source.py              # Source management (add/remove/list)
│   ├── search.py              # Enhanced search with rich output
│   ├── status.py              # Rich collection status
│   └── config.py              # Configuration management
└── config/                     # CLI-specific configuration
```

#### 3.2 Rich Progress Indicators
```python
# packages/indexed-cli/src/indexed_cli/ui/progress.py

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console
from contextlib import contextmanager

console = Console()

@contextmanager
def indexing_progress():
    """Progress context for document indexing."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        yield progress

# Usage in commands
def index_documents(source_path: str):
    with indexing_progress() as progress:
        task = progress.add_task("Loading documents...", total=100)
        # Document loading logic
        progress.update(task, advance=30)
        
        progress.update(task, description="Creating embeddings...")
        # Embedding creation
        progress.update(task, advance=50)
        
        progress.update(task, description="Building index...")
        # Index building
        progress.update(task, completed=100)
```

#### 3.3 Rich Search Results
```python
# packages/indexed-cli/src/indexed_cli/ui/tables.py

from rich.table import Table
from rich.console import Console
from rich.text import Text

def display_search_results(results, query: str):
    """Display search results in a rich table."""
    console = Console()
    
    # Header with query
    console.print(f"\n🔍 Search results for: [bold cyan]{query}[/bold cyan]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Score", style="green", width=8)
    table.add_column("Document", style="blue", width=40)
    table.add_column("Preview", style="white", width=60)
    
    for result in results[:10]:  # Top 10 results
        score = f"{result.score:.3f}"
        doc_name = result.metadata.get("filename", "Unknown")
        preview = result.text[:100] + "..." if len(result.text) > 100 else result.text
        
        table.add_row(score, doc_name, preview)
    
    console.print(table)
    console.print(f"\nShowing {len(results[:10])} of {len(results)} results\n")
```

#### 3.4 Interactive Setup Wizard
```python
# packages/indexed-cli/src/indexed_cli/commands/init.py

import typer
from rich.prompt import Prompt, Confirm
from rich.console import Console
from pathlib import Path

console = Console()

@app.command()
def init():
    """Interactive setup wizard for indexed CLI."""
    
    console.print("\n[bold green]🚀 Welcome to indexed CLI![/bold green]")
    console.print("Let's set up your first document collection.\n")
    
    # Ask for collection name
    collection_name = Prompt.ask(
        "What would you like to call your collection?",
        default="my-docs"
    )
    
    # Ask for source type
    source_type = Prompt.ask(
        "What type of documents do you want to index?",
        choices=["files", "confluence", "jira"],
        default="files"
    )
    
    if source_type == "files":
        # File path selection
        default_path = str(Path.cwd() / "docs")
        source_path = Prompt.ask(
            "Path to your documents",
            default=default_path
        )
        
        if not Path(source_path).exists():
            console.print(f"[red]Path {source_path} doesn't exist[/red]")
            raise typer.Exit(1)
    
    # Confirm and create
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"Collection: {collection_name}")
    console.print(f"Source: {source_type}")
    console.print(f"Path: {source_path}")
    
    if Confirm.ask("\nCreate this collection?"):
        # Create collection using new core library
        console.print("\n[green]✓[/green] Collection created successfully!")
        console.print(f"Run [cyan]indexed search 'your query'[/cyan] to start searching.")
```

#### 3.5 Enhanced Configuration Management
```python
# packages/indexed-cli/src/indexed_cli/config/manager.py

from rich.console import Console
from rich.table import Table
import typer

console = Console()

@app.command("config")
def config_manager(
    list_all: bool = typer.Option(False, "--list", help="List all configuration"),
    set_key: str = typer.Option(None, "--set", help="Set configuration key"),
    value: str = typer.Option(None, "--value", help="Configuration value"),
):
    """Manage indexed CLI configuration."""
    
    if list_all:
        # Display current configuration in a rich table
        table = Table(title="Current Configuration")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_column("Description", style="white")
        
        # Load and display settings
        settings = load_settings()
        for key, value in settings.items():
            table.add_row(key, str(value), get_setting_description(key))
        
        console.print(table)
    
    elif set_key and value:
        # Set configuration value
        update_setting(set_key, value)
        console.print(f"[green]✓[/green] Set {set_key} = {value}")
```

## 🔄 Implementation Timeline & Milestones

### Week 1-2: Monorepo Migration
- [ ] Create monorepo structure using uv
- [ ] Move code to new packages
- [ ] Update all import paths
- [ ] Verify all commands still work
- [ ] Update CI/CD for new structure

### Week 3-5: Core Library Rewrite
- [ ] Implement LlamaIndex SearchEngine
- [ ] Create document connectors
- [ ] Add configuration enhancements
- [ ] Implement data migration tools
- [ ] Feature flag switching between legacy/new

### Week 6-8: Enhanced CLI
- [ ] Add Rich UI components
- [ ] Create interactive setup wizard
- [ ] Enhanced search result display
- [ ] Progress indicators for long operations
- [ ] Configuration management commands

### Week 9: Integration & Testing
- [ ] End-to-end testing
- [ ] Performance benchmarking
- [ ] Documentation updates
- [ ] Migration guides

## 🎯 Success Metrics

### Functional Requirements Met
- [ ] All current commands work with new architecture
- [ ] Performance maintained or improved
- [ ] New rich CLI experience
- [ ] LlamaIndex integration complete
- [ ] Monorepo structure enables future extensions

### Technical Requirements Met
- [ ] Packages can be installed independently
- [ ] CLI + MCP server in single package
- [ ] Core library can be used by future server
- [ ] Configuration is backward compatible
- [ ] Data migration path exists

### User Experience Requirements Met
- [ ] Sub-2 minute setup for new users
- [ ] Rich progress indicators during indexing
- [ ] Beautiful search result display
- [ ] Interactive configuration management
- [ ] Clear error messages and help

## 🚨 Risk Mitigation

### Technical Risks
1. **LlamaIndex API changes**: Pin versions, abstract interfaces
2. **Performance regression**: Benchmark before/after migration
3. **Data compatibility**: Thorough migration testing
4. **Import complexity**: Clear documentation and examples

### User Experience Risks
1. **Command changes**: Maintain backward compatibility
2. **Configuration migration**: Auto-migration with fallbacks
3. **Learning curve**: Interactive help and tutorials
4. **Existing data**: Migration path and validation

This comprehensive plan maintains the working functionality while modernizing the architecture and dramatically improving the user experience. The phased approach allows for validation at each step while minimizing disruption to existing users.