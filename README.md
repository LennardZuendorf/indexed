# Indexed - Document Indexing and Semantic Search

> **Note**: This project uses a monorepo structure. The CLI has been restructured and simplified. See [MIGRATION.md](./MIGRATION.md) for migration details.

A privacy-first document indexing and semantic search tool that supports Jira, Confluence, and local files. Can be integrated with AI agents via MCP (Model Context Protocol).

**Key Features:**
- 🔒 **Privacy-First**: All processing and storage happens locally (no data sent to third parties)
- 🧠 **Semantic Search**: Understands meaning, not just keywords using vector embeddings
- ⚡ **Fast Setup**: Simple installation with `uv` and intuitive CLI commands
- 🔌 **MCP Integration**: Works with AI agents like Claude, ChatGPT via Model Context Protocol
- 📁 **Multiple Sources**: Index from local files, Jira, and Confluence

## Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [Architecture](#architecture)
- [Usage](#usage)
- [MCP Integration](#mcp-integration)
- [Documentation](#documentation)
- [Development](#development)

## Quick Start

```bash
# 1. Clone and setup
git clone <repository-url>
cd indexed-python
uv sync

# 2. Create a collection from local files
uv run indexed create files -n my-docs -p ./documents

# 3. List collections
uv run indexed inspect

# 4. Search across all collections
uv run indexed search "your query"

# 5. Search a specific collection
uv run indexed search "your query" -c my-docs
```

## Overview

### What It Does

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

### Project Resources

- 📖 [Medium Article](https://medium.com/@shnax0210/mcp-tool-for-vector-search-in-confluence-and-jira-6beeade658ba) - Original project announcement
- 🐛 [Issue Tracker](https://github.com/shnax0210/documents-vector-search/issues) - Report bugs or request features
- ⭐ **Star the repo** if you find it useful!

## Common Workflow

### 1. Create Collections

Create one or more document collections by indexing sources:

```bash
# Index local documentation
uv run indexed create files -n docs -p ./documentation

# Index Jira tickets
uv run indexed create jira -n jira --url https://jira.company.com --jql "project = PROJ"

# Index Confluence pages
uv run indexed create confluence -n wiki --url https://wiki.company.com --cql "space = SPACE"
```

Collections are stored in `./data/collections/{name}/` and contain:
- Document metadata and content
- FAISS vector indexes
- Embedding information
- Collection manifest

Indexing time depends on document count and your machine's resources.

### 2. Search Collections

Search across all collections or a specific one:

```bash
# Search all collections
uv run indexed search "how to deploy the application"

# Search specific collection
uv run indexed search "authentication" -c docs

# Limit results and use compact view
uv run indexed search "error handling" -l 10 --compact
```

### 3. Manage Collections

Inspect, update, or delete collections:

```bash
# View all collections
uv run indexed inspect

# View specific collection details
uv run indexed inspect -c docs

# Update a collection with new documents
uv run indexed update -c docs

# Delete a collection
uv run indexed delete -c old-collection
```

### 4. MCP Integration (AI Agents)

Use indexed as a tool for AI agents like Claude or ChatGPT:

```bash
# Start MCP server
uv run indexed mcp
```

See [MCP Integration](#mcp-integration) below for configuration details.

---

**Pro Tip**: Create separate collections for different contexts (e.g., "backend-docs", "frontend-docs", "jira-bugs") to enable more targeted searches.

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

## Detailed Usage

### Creating Collections

#### Local Files

Index documents from your local filesystem:

```bash
# Basic usage
uv run indexed create files -n my-docs -p /path/to/documents

# With include/exclude patterns
uv run indexed create files -n filtered-docs -p ./docs \
  --include "*.md" --include "*.txt" \
  --exclude "**/node_modules/**"
```

**Options:**
- `-n, --name` - Collection name (required)
- `-p, --path` - Path to documents folder (required)
- `--include` - Include file patterns (can be used multiple times)
- `--exclude` - Exclude file patterns (can be used multiple times)

**Supported file formats** (via [Unstructured](https://docs.unstructured.io/welcome#supported-file-types)):
- Documents: `.pdf`, `.docx`, `.pptx`, `.xlsx`
- Text: `.md`, `.txt`, `.rst`, `.html`
- Code: `.py`, `.js`, `.java`, etc.
- And many more...

#### Jira

Index tickets from Jira (Cloud or Server/Data Center):

```bash
# Jira Cloud
export ATLASSIAN_EMAIL="your-email@company.com"
export ATLASSIAN_TOKEN="your-api-token"  # Generate at https://id.atlassian.com/manage/api-tokens

uv run indexed create jira -n jira-bugs \
  --url https://your-domain.atlassian.net \
  --jql "project = PROJ AND created >= -90d"

# Jira Server/Data Center
export JIRA_TOKEN="your-bearer-token"

uv run indexed create jira -n jira-bugs \
  --url https://jira.company.com \
  --jql "project = PROJ AND status = 'In Progress'"
```

**Authentication:**
- **Cloud**: Use `ATLASSIAN_EMAIL` + `ATLASSIAN_TOKEN`
- **Server/DC**: Use `JIRA_TOKEN` (or `JIRA_LOGIN` + `JIRA_PASSWORD`)

The CLI automatically detects Cloud vs Server based on the URL (`.atlassian.net` = Cloud).

#### Confluence

Index pages from Confluence (Cloud or Server/Data Center):

```bash
# Confluence Cloud
export ATLASSIAN_EMAIL="your-email@company.com"
export ATLASSIAN_TOKEN="your-api-token"

uv run indexed create confluence -n wiki \
  --url https://your-domain.atlassian.net \
  --cql "space = 'DOCS' AND created >= '2024-01-01'"

# Confluence Server/Data Center
export CONF_TOKEN="your-bearer-token"

uv run indexed create confluence -n wiki \
  --url https://confluence.company.com \
  --cql "space = 'DOCS'"
```

**Authentication:**
- **Cloud**: Use `ATLASSIAN_EMAIL` + `ATLASSIAN_TOKEN`
- **Server/DC**: Use `CONF_TOKEN` (or `CONF_LOGIN` + `CONF_PASSWORD`)

### Searching

Perform semantic searches across your collections:

```bash
# Search all collections
uv run indexed search "how to authenticate users"

# Search specific collection
uv run indexed search "API endpoints" -c docs

# Limit results
uv run indexed search "error handling" -l 10

# Compact view (list format)
uv run indexed search "deployment" --compact

# Hide content previews
uv run indexed search "config" --no-content
```

**Options:**
- `-c, --collection` - Search specific collection only
- `-l, --limit` - Number of results per collection (default: 5)
- `--compact` - Show results in compact list view
- `--no-content` - Hide content previews

### Managing Collections

```bash
# List all collections
uv run indexed inspect

# Show details for specific collection
uv run indexed inspect -c my-docs

# Update a collection (refresh with new/changed documents)
uv run indexed update -c my-docs

# Delete a collection
uv run indexed delete -c old-collection
```

### Configuration

```bash
# Show current configuration
uv run indexed config show

# Initialize new configuration file
uv run indexed config init
```

### Legacy Commands

For backward compatibility, legacy script-style commands are available:

```bash
uv run indexed legacy <command>
```

See `uv run indexed legacy --help` for details.

## MCP Integration

Indexed can be used as a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server, allowing AI agents like Claude Desktop, ChatGPT, and others to search your document collections.

### Quick Start

```bash
# Start the MCP server
uv run indexed mcp
```

### Configuration

Add this to your MCP client configuration:

**For Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "indexed-search": {
      "command": "uv",
      "args": [
        "--directory",
        "/full/path/to/indexed-python",
        "run",
        "indexed",
        "mcp"
      ]
    }
  }
}
```

**For VS Code + GitHub Copilot** (`.vscode/mcp.json` in your project root):

```json
{
  "servers": {
    "indexed-search": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "/full/path/to/indexed-python",
        "run",
        "indexed",
        "mcp"
      ]
    }
  }
}
```

**Important:** Replace `/full/path/to/indexed-python` with the actual absolute path to this project.

### Available Tools

Once configured, the AI agent can use these tools:

- **`search`** - Search across all collections using semantic similarity
- **`search_collection`** - Search within a specific collection

### Available Resources

- **`resource://collections`** - List of all collection names
- **`resource://collections/status`** - Detailed status for all collections
- **`resource://collections/{name}`** - Status for a specific collection

### Usage Examples

Once the MCP server is configured, you can ask your AI agent:

- *"Search for authentication methods across all my collections"*
- *"Find documentation about API endpoints in the confluence collection"*
- *"What collections are available and how many documents do they contain?"*
- *"Search for bug reports related to login issues in the jira collection"*

### Environment Variable Configuration

Customize MCP server behavior with environment variables:

**Search Settings:**
- `INDEXED_MCP_MAX_DOCS` - Max documents per search (default: 10)
- `INDEXED_MCP_MAX_CHUNKS` - Max text chunks per search (default: 30)
- `INDEXED_MCP_INCLUDE_FULL_TEXT` - Include full document text (default: false)
- `INDEXED_MCP_INCLUDE_ALL_CHUNKS` - Include all chunks (default: false)
- `INDEXED_MCP_INCLUDE_MATCHED_CHUNKS` - Include only matching chunks (default: false)
- `INDEXED_MCP_DEFAULT_INDEXER` - Default indexer (default: indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2)

**Inspect Settings:**
- `INDEXED_MCP_INCLUDE_INDEX_SIZE` - Calculate index size (default: false, may be slower)

**Example with custom settings:**

```json
{
  "mcpServers": {
    "indexed-search": {
      "command": "uv",
      "args": ["--directory", "/path/to/indexed-python", "run", "indexed", "mcp"],
      "env": {
        "INDEXED_MCP_MAX_DOCS": "20",
        "INDEXED_MCP_INCLUDE_MATCHED_CHUNKS": "true",
        "INDEXED_MCP_INCLUDE_INDEX_SIZE": "true"
      }
    }
  }
}
```


## Technical Details

### Collection Storage Structure

Collections are stored in `./data/collections/{collection-name}/`:

```
./data/collections/my-docs/
├── documents/              # Document metadata and content
│   ├── doc_001.json
│   ├── doc_002.json
│   └── ...
├── indexes/                # FAISS vector indexes
│   ├── index_info.json    # Index metadata
│   ├── indexer_FAISS_*/   # FAISS index files
│   └── mappings/          # Document-to-vector mappings
└── manifest.json           # Collection metadata
```

**manifest.json** contains:
- Collection name and creation timestamp
- Last update time
- Document count and statistics
- Indexer configuration
- Source information (path, URL, query)

### Incremental Updates

When you run `uv run indexed update -c my-docs`, the system:

1. Reads the `manifest.json` to find `lastModifiedDocumentTime`
2. Fetches only documents created/modified since that time (minus 1 day buffer)
3. Processes and indexes only new/changed documents
4. Updates the manifest with new statistics

This makes updates much faster than full re-indexing.

### Caching Mechanism

For Jira/Confluence sources, Indexed caches fetched documents:

- Cache location: `./data/caches/{hash}/`
- Hash is based on: URL, query (JQL/CQL), and other parameters
- Useful for development/testing to avoid repeated API calls
- Cache is used only if `{hash}_completed` marker file exists

**To bypass cache:**
- Delete the cache folder: `rm -rf ./data/caches/{hash}`
- Or run `update` command after initial creation

## Documentation

- **[MIGRATION.md](./MIGRATION.md)** - Phase 1 monorepo migration guide
- **[DEVELOPMENT.md](./DEVELOPMENT.md)** - Development workflow and contribution guide
- **[.prd/](./prd/)** - Product requirements and implementation plans

## Project Structure

The project uses a monorepo structure:

```
indexed-python/
├── indexed/                   # CLI application (at root)
│   ├── src/cli/              # CLI commands and app
│   │   ├── commands/         # Command implementations
│   │   │   ├── create.py     # Collection creation
│   │   │   ├── search.py     # Search operations
│   │   │   ├── inspect.py    # Collection inspection
│   │   │   ├── config.py     # Configuration management
│   │   │   └── mcp.py        # MCP server command
│   │   ├── app.py            # Main Typer application
│   │   └── mcp.py            # MCP server implementation
│   └── pyproject.toml        # CLI package config
│
├── packages/
│   └── indexed-core/         # Core library (business logic)
│       ├── src/index/
│       │   ├── legacy/       # Legacy implementation
│       │   ├── config/       # Configuration management
│       │   ├── connectors/   # Data source connectors
│       │   ├── models/       # Data models
│       │   └── utils/        # Utilities
│       └── pyproject.toml    # Core package config
│
├── tests/                    # Test suite
│
├── data/                     # Generated data (not in git)
│   ├── collections/         # Indexed collections
│   └── caches/              # API response caches
│
├── .memory/                  # Project memory files
│   ├── architecture.md
│   ├── tech.md
│   └── brief.md
│
├── pyproject.toml            # Workspace config
├── uv.lock                   # Dependency lock file
├── DEVELOPMENT.md            # Development guide
├── MIGRATION.md              # Migration documentation
└── README.md                 # This file
```

### Key Directories

- **`indexed/`** - Main CLI application at project root
  - Commands: `create`, `search`, `inspect`, `update`, `delete`, `config`, `mcp`
  - Entry point: `uv run indexed`

- **`packages/indexed-core/`** - Core library with business logic
  - Collection management
  - Vector indexing and search
  - Document connectors (Files, Jira, Confluence)
  - Embedding and storage services

- **`data/`** - Runtime data (auto-generated, gitignored)
  - `collections/` - All indexed collections
  - `caches/` - API response caches (Jira/Confluence)

- **`tests/`** - Test suite for both CLI and core library

## CLI Commands Reference

### Available Commands

```bash
uv run indexed --help                          # Show all commands
uv run indexed <command> --help                # Show command-specific help
```

| Command | Description |
|---------|-------------|
| `create files` | Create collection from local files |
| `create jira` | Create collection from Jira tickets |
| `create confluence` | Create collection from Confluence pages |
| `search` | Search collections using semantic similarity |
| `inspect` | View collection details and statistics |
| `update` | Refresh collection with new/updated documents |
| `delete` | Remove a collection |
| `config show` | Display current configuration |
| `config init` | Initialize new configuration file |
| `mcp` | Start MCP server for AI agent integration |
| `legacy` | Run legacy script-style commands |

### Global Options

- `--verbose` - Enable verbose (INFO) logging with rich formatting
- `--log-level LEVEL` - Set explicit logging level (DEBUG, INFO, WARNING, ERROR)
- `--json-logs` - Output logs as JSON (structured)

### Examples

```bash
# Create collection with verbose logging
uv run indexed --verbose create files -n my-docs -p ./docs

# Search with debug logging
uv run indexed --log-level DEBUG search "query"

# Get help for specific command
uv run indexed create files --help
```

## Contributing

See [DEVELOPMENT.md](./DEVELOPMENT.md) for setup instructions and development workflow.

## License

See [LICENSE](./LICENSE) file for details.
