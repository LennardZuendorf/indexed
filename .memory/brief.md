# Project Brief - Indexed

## Product Overview

**Product Name**: Indexed  
**Version**: 1.0.0  
**Status**: Production Ready  
**Last Updated**: 2025-10-15

## What is Indexed?

Indexed is a privacy-first command-line tool for semantic document search built on modern vector search technology (FAISS + embeddings). It allows developers to index local and remote documents (Jira, Confluence, local files) and perform fast semantic searches without sending data to third parties.

Think of it as building your own private search engine for your institutional knowledge - documentation, tickets, notes, and more - that understands meaning, not just keywords.

## Core Value Proposition

1. **Privacy-First**: All processing and storage happens locally
2. **Semantic Search**: Understands meaning, not just keywords
3. **Simple Setup**: Fast installation and intuitive CLI commands
4. **Developer-Friendly**: Clean CLI interface with helpful output

## Target Users

**Primary User: Individual Developer** 👨‍💻
- Software engineers, researchers, technical writers
- Need to search through project documentation, notes, code comments
- Want fast, semantic search through personal document collections
- Value privacy and local-first approach

## Project Structure

### Monorepo Layout
```
indexed/
├── indexed/                  # Main CLI application
│   └── src/indexed/         # CLI commands, MCP server
├── packages/
│   ├── indexed-core/        # Core library (core.v1 API)
│   ├── indexed-connectors/  # Document source connectors
│   └── utils/               # Shared utilities
├── tests/                   # Test suite
└── data/                    # Local data storage (gitignored)
```

### Architecture Overview

**Core Components:**
- **`core.v1`**: Clean API for indexing and search (`Index`, `Config` classes)
- **Connectors**: Protocol-based connector system (Files, Jira, Confluence)
- **CLI**: Typer-based commands with Rich output formatting
- **MCP Server**: FastMCP integration for AI agents (Claude, ChatGPT, etc.)
- **Configuration**: Pydantic-based config management with TOML files

**Design Philosophy:**
- KISS (Keep It Simple, Stupid) - simplicity over complexity
- Privacy-first - local processing by default
- Type-safe - Pydantic validation and type hints throughout
- Versioned API - `core.v1` with clean upgrade paths
- UX-first - CLI designed for excellent developer experience

## Key Features

**Document Indexing:**
- Multi-source indexing (Jira, Confluence, Local Files)
- Support for 20+ file formats (PDF, DOCX, MD, TXT, etc.)
- Incremental updates (reindex only changed documents)
- Configurable include/exclude patterns

**Search & Retrieval:**
- Semantic search using FAISS vector similarity
- Local embeddings (sentence-transformers) - no data sent to cloud
- Search across all collections or target specific ones
- Configurable result limits and similarity thresholds

**Collection Management:**
- Create, update, inspect, and remove collections
- Per-collection configuration and caching
- Collection-level statistics and metadata

**Developer Integration:**
- MCP (Model Context Protocol) server for AI agents
- Works with Claude, ChatGPT, Cursor, and other MCP-compatible tools
- Clean Python API for programmatic access (`core.v1`)
- Rich CLI output with colors and formatting

**Configuration:**
- TOML-based configuration (`indexed.toml`)
- Environment variable support (`.env` files)
- Per-collection and global settings
- Sensible defaults for quick start

## Usage Examples

### Typical Workflow

**Python API (Core V1)**
```python
# Collection-based API
from core.v1 import Index, Config
from core.v1.connectors import JiraConnector, FileSystemConnector

# Initialize
config = Config.from_file("indexed.toml")  # Reads [indexer.v1] section
index = Index(config)

# Add collections
jira = JiraConnector(config)
index.add_collection(jira, name="jira")

files = FileSystemConnector('./docs')
index.add_collection(files, name="docs")

# Search all collections
results = index.search("authentication methods")

# Search specific collection
results = index.search(collection="jira", query="What was project xyz?")

# Inspect
stats = index.inspect()  # All collections
stats = index.inspect(collection="jira")  # Specific collection
```

**CLI Commands**
```bash
# Search operations (primary use case)
indexed index search "authentication methods"     # All collections
indexed index search "query" --collection jira    # Specific collection

# Collection management
indexed index create files --collection docs --path ./docs
indexed index create jira --collection issues --url <url> --jql <query>
indexed index create confluence --collection pages --url <url> --cql <query>
indexed index inspect                             # Show all collections
indexed index inspect docs                        # Inspect specific collection
indexed index update docs                         # Refresh a collection
indexed index remove docs                         # Remove a collection

# Configuration management
indexed config inspect
indexed config init
indexed config set KEY VALUE
indexed config validate
indexed config reset

# MCP server for AI agents
indexed mcp run
indexed mcp dev
```

**Config File (Versioned)**
```toml
# indexed.toml
[indexer.v1]
embedding_model = "all-MiniLM-L6-v2"
storage_path = ".indexed/v1"  # Automatically versioned
chunk_size = 512
```

## Technical Foundation

**Core Stack:**
- Python 3.10+ (using uv for package management)
- FAISS for vector storage
- Sentence-transformers / OpenAI / Voyage AI for embeddings
- Typer for CLI framework
- FastMCP for AI agent integration
- Pydantic for configuration and data validation

**Architecture Principles:**
1. **KISS First**: Simple, clean API over complex patterns
2. **Versioned API**: `core.v1` with versioned config and storage (`.indexed/v1/`)
3. **Dual CLI**: Separate index commands (operations) and config commands (management)
4. **Monorepo Structure**: Clean separation of apps and packages
5. **Type Safety**: Type hints where they add value, Pydantic for config validation

## Release Status

**v1.0 - Production Ready** ✅
- All core features implemented and tested
- Clean architecture with `core.v1` API
- CLI commands fully functional
- MCP server integration working
- Documentation complete

**Future enhancements tracked via GitHub Issues**

## Development Principles

**KISS (Keep It Simple, Stupid)**
- Start with simplest solution that works
- Add complexity only when needed
- Prefer clarity over cleverness

**Quality First**
- Type hints and validation everywhere
- Comprehensive testing
- Clear error messages
- Good documentation

**Privacy & Local-First**
- Default to local processing
- Cloud features are optional
- User data never leaves their machine (unless explicitly configured)

## Additional Documentation

- **Architecture**: `.memory/architecture.md` - System design and patterns
- **Tech Stack**: `.memory/tech.md` - Technology choices and coding standards
- **Development**: Root `README.md` and package READMEs for setup instructions
- **Tasks**: GitHub Issues for feature requests and bugs
