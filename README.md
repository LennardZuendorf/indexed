<p align="left">
  <img src="./docs/img/logo.png" alt="Indexed Logo" width="500"/>
  <h3>
    Index Institutional Knowledge
    and Make it Available for AI Agents and LLMs! 
  </h3>
</p>

[![Python Build, Check, Test](https://github.com/LennardZuendorf/indexed/actions/workflows/python-package.yml/badge.svg)](https://github.com/LennardZuendorf/indexed/actions/workflows/python-package.yml) [![codecov](https://codecov.io/github/LennardZuendorf/indexed/graph/badge.svg?token=6P99FW1Z1A)](https://codecov.io/github/LennardZuendorf/indexed) ![Libraries.io dependency status for GitHub repo](https://img.shields.io/librariesio/github/lennard.zuendorf/indexed)


A privacy-first document indexing and semantic search tool that supports Jira, Confluence, and local files. Integrates with AI agents via MCP (Model Context Protocol).

> [!WARNING]
> Indexed is currently in a very early alpha stage!

**Key Features:**
- 🔒 **Privacy-First**: All processing and storage happens locally - no data sent to third parties
- 🧠 **Semantic Search**: Understands meaning, not just keywords, using vector embeddings
- ⚡ **Fast Setup**: Simple installation and usage with `uv` and intuitive CLI commands
- 🔌 **MCP Integration**: Works with AI agents like Claude, Cursor, and Cline via Model Context Protocol
- 📁 **Multiple Sources**: Index from local files, Jira (Cloud & Server), and Confluence (Cloud & Server)

## Table of Contents

- [Quick Start](#quick-start)
- [What It Does](#what-it-does)
- [Installation](#installation)
- [Usage](#usage)
- [MCP Integration](#mcp-integration)
- [Docker](#docker)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [License](#license)

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/LennardZuendorf/indexed.git
cd indexed
uv sync

# 2. Create a collection from local files
uv run indexed index create --type files --name my-docs

# 3. Search your collections
uv run indexed index search "your query"

# 4. Start MCP server for AI agents
uv run indexed mcp
```

For detailed usage examples, see the [CLI Documentation](./indexed/README.md).

## What It Does

**Indexed** creates searchable collections of documents and finds information using natural language queries (semantic search). Instead of exact keyword matching, it understands the *meaning* of your queries.

### Capabilities

| Source | Description |
|--------|-------------|
| **Local Files** | Index documents: `.pdf`, `.pptx`, `.docx`, `.md`, and more |
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
- **[Unstructured](https://github.com/Unstructured-IO/unstructured)** – Multi-format document parsing
- **[Typer](https://typer.tiangolo.com/)** – Modern CLI framework
- **[Rich](https://rich.readthedocs.io/)** – Beautiful terminal output
- **[FastMCP](https://github.com/jlowin/fastmcp)** – Model Context Protocol server

## Installation

### Prerequisites

1. **Python 3.10+**
2. **[uv](https://docs.astral.sh/uv/)** – Fast Python package manager

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd indexed

# Install dependencies
uv sync

# Verify installation
uv run indexed --help
```

## Usage

### Creating Collections

```bash
# Local files
uv run indexed index create --type files --name docs

# Jira (Cloud)
uv run indexed index create --type jiraCloud --name jira-issues

# Confluence (Cloud)
uv run indexed index create --type confluenceCloud --name wiki
```

### Searching

```bash
# Search all collections
uv run indexed index search "authentication methods"

# Search specific collection
uv run indexed index search "bug reports" --collection jira-issues

# JSON output for scripting
uv run indexed index search "API docs" --json
```

### Managing Collections

```bash
# List all collections
uv run indexed index inspect

# Inspect specific collection
uv run indexed index inspect my-docs

# Update a collection
uv run indexed index update my-docs

# Delete a collection
uv run indexed index delete my-docs
```

### Configuration

```bash
# View configuration
uv run indexed config get all

# Set a value
uv run indexed config set search.max_docs 20

# Validate configuration
uv run indexed config validate
```

For the complete CLI reference, see the [CLI Documentation](./indexed/README.md).

## MCP Integration

Indexed provides an MCP server for AI agent integration. Use it with Claude Desktop, Cursor, Cline, and other MCP-compatible tools.

### Starting the MCP Server

```bash
# Default (stdio transport for Claude Desktop)
uv run indexed mcp

# HTTP server mode
uv run indexed mcp --transport http --port 8000
```

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

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

### Cursor Configuration

Add to your Cursor MCP settings:

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

## Docker

Run indexed in a Docker container for isolated, reproducible deployments.

### Building the Image

```bash
docker build -t indexed .
```

### Running the MCP Server

```bash
# Default: stdio transport (for Claude Desktop pipe)
docker run -i -v ~/.indexed:/root/.indexed indexed

# HTTP transport (for network access)
docker run -p 8000:8000 -v ~/.indexed:/root/.indexed indexed mcp --transport http --host 0.0.0.0

# SSE transport
docker run -p 8000:8000 -v ~/.indexed:/root/.indexed indexed mcp --transport sse --host 0.0.0.0
```

### Managing Collections in Docker

```bash
# Create a collection from local files
docker run -v ~/.indexed:/root/.indexed -v /path/to/docs:/docs \
  indexed index create --type files --name my-docs --path /docs

# Search collections
docker run -v ~/.indexed:/root/.indexed indexed index search "your query"

# Inspect collections
docker run -v ~/.indexed:/root/.indexed indexed index inspect
```

### Docker Compose

For HTTP-based deployments, use the included `docker-compose.yml`:

```bash
# Start HTTP server
docker compose up indexed-http

# Run CLI commands
docker compose run indexed-cli index inspect
```

### Volume Mounts

| Container Path | Purpose |
|----------------|---------|
| `/root/.indexed` | Configuration and data storage |
| `/docs` (example) | Mount local files for indexing |

### Environment Variables

Configure via `INDEXED__` prefix:

```bash
docker run -e INDEXED__mcp__log_level=DEBUG indexed mcp
```

## Project Structure

The project uses a monorepo structure with independent packages:

```
indexed/
├── indexed/                   # Main CLI and MCP server
│   ├── src/indexed/          # CLI commands and MCP implementation
│   └── README.md             # 📖 CLI documentation
│
├── packages/
│   ├── indexed-core/         # Core indexing and search library
│   │   ├── src/core/         # Business logic and services
│   │   └── README.md         # 📖 Core library docs
│   │
│   ├── indexed-config/       # Configuration management
│   │   ├── src/indexed_config/
│   │   └── README.md         # 📖 Config system docs
│   │
│   ├── indexed-connectors/   # Document source connectors
│   │   ├── src/connectors/   # Jira, Confluence, Files connectors
│   │   └── README.md         # 📖 Connector docs
│   │
│   └── utils/                # Shared utilities
│       ├── src/utils/        # Logging, retry, batching, etc.
│       └── README.md         # 📖 Utilities docs
│
├── tests/                    # Test suite
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
| [Connectors](./packages/indexed-connectors/README.md) | Source integrations |
| [Utilities](./packages/utils/README.md) | Shared utilities |

## License

See [LICENSE](./LICENSE) file for details.

## Credits

The Core v1 implementation is based on [documents-vector-search](https://github.com/shnax0210/documents-vector-search) by shnax0210, licensed under MIT and modified extensively.

## Resources

- 📖 [Medium Article](https://medium.com/@shnax0210/mcp-tool-for-vector-search-in-confluence-and-jira-6beeade658ba) – Original project announcement
- 🐛 [Issue Tracker](https://github.com/shnax0210/documents-vector-search/issues) – Report bugs or request features
- ⭐ **Star the repo** if you find it useful!
