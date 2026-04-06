<div align="center">

<img src="./docs/img/logo.png" alt="Indexed Logo" width="500"/>

### Index everything. Code, docs, and knowledge — one MCP, zero cloud.

[![License: Sustainable Use](https://img.shields.io/badge/License-Sustainable%20Use-blue)](#license)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](#)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-5A45FF)](#mcp-integration)

[![Python Full Test Suite with Coverage](https://github.com/LennardZuendorf/indexed/actions/workflows/python-cov.yml/badge.svg)](https://github.com/LennardZuendorf/indexed/actions/workflows/python-cov.yml) [![Python Build and System Tests](https://github.com/LennardZuendorf/indexed/actions/workflows/python-ci.yml/badge.svg)](https://github.com/LennardZuendorf/indexed/actions/workflows/python-ci.yml) [![codecov](https://codecov.io/gh/LennardZuendorf/indexed/graph/badge.svg?token=6P99FW1Z1A)](https://codecov.io/gh/LennardZuendorf/indexed)

[Quickstart](#quick-start) · [Documentation](https://indexed.sh/docs) · [Blog & Guides](https://indexed.sh/blog)

</div>

---

The local-first indexing engine that gives Claude Code, Cowork, Codex and other AI agents deep context over your codebase, documentation, Jira tickets, and Confluence pages.

> [!WARNING]
> Indexed is currently in a very early alpha stage!

**Key Features:**
- **Privacy-First**: All processing and storage happens locally - no data sent to third parties
- **Semantic Search**: Understands meaning, not just keywords, using dense vector embeddings
- **Fast Setup**: Simple installation and usage with `uv` and intuitive CLI commands
- **MCP Integration**: Works with Claude Code, Cowork, Cursor, Cline, and other MCP-compatible agents
- **Multiple Sources**: Index from local files, Jira (Cloud & Server), and Confluence (Cloud & Server)

## Why Indexed?

Claude Code searches your codebase on demand with grep — fast for small repos, but expensive on large ones. Every file read costs tokens. Every broad search burns context window.

Indexed fixes this. It **pre-computes a semantic search index** (dense vector embeddings via FAISS) over your code, docs, and project tools — then exposes it to Claude Code/Desktop/Cowork, Codex or any other AI Agent via MCP. The result: instant, relevant context retrieval without burning tokens on full file reads.

**What makes Indexed different:**

- **Not just code.** Index Markdown vaults, PDFs, DOCX, PPTX, images, and 25+ file formats via Docling. Works with `.md` files created by Obsidian out of the box.
- **Not just search.** Native Jira and Confluence connectors pull tickets, pages, and metadata into your index. Ask Claude about your sprint backlog or find that RFC.
- **Not cloud-dependent.** Runs entirely on your machine. HuggingFace models with ONNX optimization for embeddings, FAISS for vector storage. No API keys required.
- **Not one-shot.** Incremental updates via `indexed index update` with git-based change tracking keep your index fresh as your codebase (or second brain) evolves.

## Table of Contents

- [Quick Start](#quick-start)
- [Why Indexed?](#why-indexed)
- [What It Does](#what-it-does)
- [Installation](#installation)
- [Usage](#usage)
- [MCP Integration](#mcp-integration)
- [Docker](#docker)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [License](#license)

## Quick Start & First Index

```bash
# 1. Clone and setup
uv tool install indexed-sh

# 2. Create a collection from local files
indexed index create files --name my-docs

# 3. Test searching your collections
indexed index search "your query"

```

## MCP Integration

Indexed provides an MCP server for AI agent integration. Use it with Claude Desktop, Cursor, Cline, and other MCP-compatible tools.

### Starting the MCP Server

```bash
# Default (stdio transport for Claude Desktop)
indexed run mcp

# HTTP server mode
indexed run mcp --transport http --port 8000
```

### Claude Code



### Claude Code

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "indexed": {
      "command": "indexed ",
      "args": [
        "run",
        "mcp"
      ]
    }
  }
}
```

### MCP JSON Configuratipn

Add to the mcp.json file from your respective coding agent:

```json
{
  "mcpServers": {
    "indexed": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/indexed",
        "run",
        "indexed-mcp"
      ]
    }
  }
}
```

See [MCP Server Documentation](./indexed/README.md#mcp-server-examples) for more details.

## What It Does

**Indexed** creates searchable collections of documents and finds information using natural language queries (semantic search). Instead of exact keyword matching, it understands the *meaning* of your queries.

### Capabilities

| Source | Description |
|--------|-------------|
| **Local Files** | Index documents: `.pdf`, `.pptx`, `.docx`, `.md`, code files, images, and more |
| **Jira** | Index tickets from Cloud and Server/Data Center |
| **Confluence** | Index pages from Cloud and Server/Data Center |

### How It Works

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Index     │      │   Search    │      │   Retrieve  │
│  Documents  │  →   │   Query     │  →   │   Results   │
│ (FAISS +    │      │ (Embedding  │      │ (Relevant   │
│ Embeddings) │      │  Similarity)│      │  Chunks)    │
└─────────────┘      └─────────────┘      └─────────────┘
```

1. **Index**: Documents are chunked, embedded into vectors, and stored in a FAISS index
2. **Search**: Your query is embedded and compared against stored vectors using semantic similarity
3. **Retrieve**: The most relevant document chunks are returned with context

### Technology Stack

- **[FAISS](https://github.com/facebookresearch/faiss)** – Fast vector similarity search
- **[Sentence Transformers](https://www.sbert.net/)** – Local embedding models
- **[Docling](https://github.com/docling-project/docling)** – Rich document parsing (PDF, DOCX, PPTX, HTML, images)
- **[tree-sitter](https://tree-sitter.github.io/)** – AST-aware code chunking (Python, TypeScript, Java, Rust, Go, C/C++)
- **[Typer](https://typer.tiangolo.com/)** – Modern CLI framework
- **[Rich](https://rich.readthedocs.io/)** – Beautiful terminal output
- **[FastMCP](https://github.com/jlowin/fastmcp)** – Model Context Protocol server


## Full Usage Examples

### Prerequisites

1. **Python 3.11+**
2. **[uv](https://docs.astral.sh/uv/)** – Fast Python package manager

### Setup

#### From Pip

**This is the suggested setup:**

```bash
# Clone the repository
uv tool install indexed-sh
```

#### From Source

You can also run directly from source, indexed will automatically pick up global or local config!

```bash
# Clone the repository
uvx indexed-sh
```

#### Locally

Alternatively you can keep all code locally and run via uv run indexed (only works in the right dir):

```bash
# Clone the repository
git clone <repository-url>
cd indexed

# Install dependencies
uv sync

# Verify installation
uv run indexed --help
```


### Creating Collections

All of these commands assume you installed using uv tool install. If not you need to replace *indexed* with:

- From Source : uvx indexed-sh
- Locally: uv run indexed

```bash
# Local files
indexed index create --type files --name docs

# Jira (Cloud)
indexed index create --type jiraCloud --name jira-issues

# Confluence (Cloud)
indexed index create --type confluenceCloud --name wiki
```

### Searching

```bash
# Search all collections
indexed index search "authentication methods"

# Search specific collection
indexed index search "bug reports" --collection jira-issues

# JSON output for machine reading
indexed index search "API docs" --simple-output
```

### Managing Collections

```bash
# List all collections
indexed index inspect

# Inspect specific collection
indexed index inspect my-docs

# Update a collection
indexed index update my-docs

# Delete a collection
indexed index delete my-docs
```

### Configuration

```bash
# View configuration
indexed config get all

# Set a value
indexed config set search.max_docs 20

# Validate configuration
indexed config validate
```

For the complete CLI reference, see the [CLI Documentation](https://indexed.sh/docs/reference/config).

## Local Development and Building

The project uses [una](https://github.com/carderne/una) for monorepo wheel packaging with [hatch-una](https://pypi.org/project/hatch-una/).

### Development Setup

```bash
# Install all dependencies including dev tools
uv sync --all-groups

# Run tests
uv run pytest -q

# Lint and format
uv run ruff check .
uv run ruff format .
```

### Build a Distributable Wheel

```bash
# Build the wheel (bundles all workspace packages)
uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/indexed

# The wheel contains all code and can be installed standalone. Replace x.x.x with the build number returned above!
pip install dist/indexed-x.x.x-py3-none-any.whl
```

## Project Structure

The project uses a **uv workspace monorepo** with [una](https://github.com/carderne/una) for building distributable wheels:

```
indexed/
├── indexed/                   # Main CLI and MCP server
│   ├── src/indexed/          # CLI commands and MCP implementation
│   └── README.md             # 📖 CLI documentation
│
├── packages/
│   ├── indexed-core/         # Core indexing and search library
│   │   ├── src/core/         # Business logic and services
│   │   │    ├── v1/          # Core V1 Implementation
│   │   └── README.md         # 📖 Core library docs
│   │
│   ├── indexed-parsing/      # Shared document parsing (Docling + tree-sitter)
│   │   └── src/parsing/      # Parsers, router, code chunker
│   │
│   ├── indexed-config/       # Configuration management
│   │   ├── src/indexed_config/
│   │   └── README.md         # 📖 Config system docs
│   │
│   ├── indexed-connectors/   # Document source connectors
│   │   ├── src/connectors/   # Jira, Confluence, Files connectors -> Use shared document parsing
│   │   └── README.md         # 📖 Connector docs
│   │
│   └── utils/                # Shared utilities
│       ├── src/utils/        # Logging, retry, batching, etc.
│       └── README.md         # 📖 Utilities docs
│
├── tests/                    # Test suite, unit and system
├── docs/                     # Documentation
│
└── pyproject.toml            # Workspace configuration
```

## Documentation

| Document | Description |
|----------|-------------|
| [CLI Documentation](./indexed/README.md) | Complete usage guide for all commands |
| [Core Library](./packages/indexed-core/README.md) | Technical architecture and APIs |
| [Config System](./packages/indexed-config/README.md) | Configuration management |
| [Parsing](./packages/indexed-parsing/README.md) | Document parsing (Docling, tree-sitter) |
| [Connectors](./packages/indexed-connectors/README.md) | Source integrations |
| [Utilities](./packages/utils/README.md) | Shared utilities |

## License

See [LICENSE](./LICENSE) file for details.

## Credits

The Core v1 implementation is based on [documents-vector-search](https://github.com/shnax0210/documents-vector-search) by shnax0210, licensed under MIT and modified extensively.

## Resources

- [Indexed Website](https://indexed.sh) – Project homepage
- [Issue Tracker](https://github.com/LennardZuendorf/indexed/issues) – Report bugs or request features
- **Star the repo** if you find it useful!
