<p align="left">
  <img src="./docs/img/logo.png" alt="Indexed Logo" width="500"/>
  <h3>
    Index Institutional Knowledge
    and Make it Available for AI Agents and LLMs! 
  </h3>
</p>

A privacy-first document indexing and semantic search tool that supports Jira, Confluence, and local files. Can be integrated with AI agents via MCP (Model Context Protocol).

**Key Features:**
- 🔒 **Privacy-First**: All processing and storage happens locally (no data sent to third parties)
- 🧠 **Semantic Search**: Understands meaning, not just keywords using vector embeddings
- ⚡ **Fast Setup**: Simple installation with `uv` and intuitive CLI commands
- 🔌 **MCP Integration**: Works with AI agents like Claude, ChatGPT, Cursor via Model Context Protocol
- 📁 **Multiple Sources**: Index from local files, Jira (Cloud & Server), and Confluence (Cloud & Server)

## Table of Contents

- [Quick Start](#quick-start)
- [What It Does](#what-it-does)
- [Installation](#installation)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [License](#license)

## Quick Start

```bash
# 1. Clone and setup
git clone <repository-url>
cd indexed-python
uv sync

# 2. Create a collection (dynamic connectors)
# You'll be prompted for connector-specific settings
uv run indexed index create --type files --name my-docs

# 3. Search your collections
uv run indexed index search "your query"

# 4. Start MCP server for AI agents
uv run indexed mcp
```

For detailed usage examples, see the [CLI Documentation](./indexed/README.md).

Note:
- Legacy command (deprecated): `uv run indexed index create files -n my-docs -p ./documents`
- New dynamic flow uses typed schemas; available types: `files`, `jira`, `jiraCloud`, `confluence`, `confluenceCloud`.

## What It Does

**Indexed** lets you create searchable collections of documents and find information using natural language queries (semantic search). Instead of exact keyword matching, it understands the meaning of your queries.

**Key Capabilities:**
- **Local Files**: Index documents in various formats (.pdf, .pptx, .docx, .md, etc.)
- **Jira & Confluence**: Index tickets and pages from both Cloud and Server/Data Center
- **Semantic Search**: Find documents by meaning, not just keywords
- **MCP Protocol**: Integrate with AI agents (Claude, ChatGPT, etc.)
- **Incremental Updates**: Refresh collections without full re-indexing
- **Privacy-First**: All processing happens locally on your machine

### Technology Stack

- **[FAISS](https://github.com/facebookresearch/faiss)** - Fast vector similarity search
- **[Sentence Transformers](https://www.sbert.net/)** - Local embedding models
- **[Unstructured](https://github.com/Unstructured-IO/unstructured)** - Multi-format document parsing
- **[Typer](https://typer.tiangolo.com/)** - Modern CLI framework
- **[Rich](https://rich.readthedocs.io/)** - Beautiful terminal output
- **[FastMCP](https://github.com/jlowin/fastmcp)** - Model Context Protocol server

### How It Works

1. **Index**: Documents are chunked, embedded into vectors, and stored in a FAISS index
2. **Search**: Your query is embedded and compared against stored vectors using semantic similarity
3. **Retrieve**: The most relevant document chunks are returned with context

For technical details, see the [Core Library Documentation](./packages/indexed-core/README.md).

## Installation

### Prerequisites

1. **Python 3.10+**
2. **[uv](https://docs.astral.sh/uv/)** - Fast Python package manager

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd indexed-python

# Install dependencies
uv sync

# Verify installation
uv run indexed --help
```

For detailed usage instructions including:
- Creating collections (Files, Jira, Confluence)
- Searching and managing collections
- MCP server integration
- Authentication setup
- CLI commands reference

See the **[CLI Documentation](./indexed/README.md)**

## Project Structure

The project uses a monorepo structure with independent packages:

```
indexed-python/
├── indexed/                   # Main CLI and MCP server
│   ├── src/cli/              # CLI commands and MCP implementation
│   └── pyproject.toml        # 📖 See: indexed/README.md
│
├── packages/
│   ├── indexed-core/         # Core indexing and search library
│   │   ├── src/core/         # Business logic and services
│   │   └── pyproject.toml    # 📖 See: packages/indexed-core/README.md
│   │
│   ├── indexed-connectors/   # Document source connectors
│   │   ├── src/connectors/   # Jira, Confluence, Files connectors
│   │   └── pyproject.toml    # 📖 See: packages/indexed-connectors/README.md
│   │
│   └── utils/                # Shared utilities
│       ├── src/utils/        # Logging, retry, batching, etc.
│       └── pyproject.toml    # 📖 See: packages/utils/README.md
│
├── tests/                    # Test suite
├── data/                     # Runtime data (gitignored)
│   ├── collections/         # Indexed document collections
│   └── caches/              # API response caches
│
└── pyproject.toml            # Workspace configuration
```

### Package Documentation

- **[indexed/](./indexed/README.md)** - CLI commands, MCP server, usage examples
- **[indexed-core/](./packages/indexed-core/README.md)** - Core library architecture and APIs
- **[indexed-connectors/](./packages/indexed-connectors/README.md)** - Document connector implementations
- **[utils/](./packages/utils/README.md)** - Shared utility functions

## Documentation

- **[CLI Documentation](./indexed/README.md)** - Complete usage guide
- **[Core Library](./packages/indexed-core/README.md)** - Technical architecture
- **[Connectors](./packages/indexed-connectors/README.md)** - Source integrations
- **[DEVELOPMENT.md](./DEVELOPMENT.md)** - Development workflow
- **[MIGRATION.md](./MIGRATION.md)** - Migration guide

## License

See [LICENSE](./LICENSE) file for details.

## Credits

The Core v1 implementation is based on [documents-vector-search](https://github.com/shnax0210/documents-vector-search) by shnax0210, licensed under MIT and modified extensively.

## Resources

- 📖 [Medium Article](https://medium.com/@shnax0210/mcp-tool-for-vector-search-in-confluence-and-jira-6beeade658ba) - Original project announcement
- 🐛 [Issue Tracker](https://github.com/shnax0210/documents-vector-search/issues) - Report bugs or request features
- ⭐ **Star the repo** if you find it useful!

