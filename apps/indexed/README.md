# indexed

Command-line interface and MCP server for semantic document search with AI agent integration.

## Overview

`indexed` provides a powerful CLI and MCP (Model Context Protocol) server for creating, managing, and searching document collections using semantic similarity. It enables AI agents and LLMs to access institutional knowledge from various sources including Jira, Confluence, and local files.

## Features

### CLI Commands

| Command | Description |
|---------|-------------|
| `index create` | Create document collections from various sources |
| `index search` | Semantic search across collections |
| `index update` | Update existing collections with latest data |
| `index remove` | Remove collections with confirmation |
| `index inspect` | View collection metadata and statistics |
| `config` | Manage configuration (get, set, validate) |
| `mcp` | Start MCP server for AI agent integration |
| `info` | Display system and storage information |

### Supported Source Types

| Type | Description |
|------|-------------|
| `files` | Local files and directories |
| `jira` | Jira Server/Data Center |
| `jiraCloud` | Jira Cloud (Atlassian hosted) |
| `confluence` | Confluence Server/Data Center |
| `confluenceCloud` | Confluence Cloud (Atlassian hosted) |

### MCP Server

FastMCP-based server providing tools and resources for AI agents:

**Tools:**
- `search` – Search across all collections
- `search_collection` – Search within a specific collection

**Resources:**
- `resource://collections` – List of available collection names
- `resource://collections/status` – Detailed status for all collections
- `resource://collections/{name}` – Detailed status for specific collection

**Transport Modes:**
- `stdio` – Standard I/O for Claude Desktop, Cline, etc. (default)
- `http` – HTTP server mode
- `sse` – Server-Sent Events mode
- `streamable-http` – Streamable HTTP mode

## Installation

This package is part of the indexed monorepo workspace. Requires **Python 3.11+**.

```bash
# Install all dependencies including development tools
uv sync --all-groups

# Install production dependencies only
uv sync

# Build a standalone distributable wheel
uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/indexed
```

## CLI Usage

### Creating Collections

```bash
# Create from local files (interactive prompts)
uv run indexed index create --type files --name my-docs

# Create from Jira Cloud
uv run indexed index create --type jiraCloud --name my-issues

# Create from Confluence Cloud
uv run indexed index create --type confluenceCloud --name wiki
```

### Searching

```bash
# Search across all collections
uv run indexed index search "authentication methods"

# Search specific collection
uv run indexed index search "bug reports" --collection my-issues

# Compact output (titles only)
uv run indexed index search "API documentation" --compact

# JSON output for scripting
uv run indexed index search "config" --json
```

### Managing Collections

```bash
# Inspect all collections
uv run indexed index inspect

# Inspect specific collection
uv run indexed index inspect my-issues

# Update a collection
uv run indexed index update my-issues

# Remove a collection
uv run indexed index remove my-issues
```

### Configuration

```bash
# View all configuration
uv run indexed config get all

# Get specific value
uv run indexed config get search.max_docs

# Set configuration value
uv run indexed config set search.max_docs 20

# Validate configuration
uv run indexed config validate
```

### System Information

```bash
# Display system and storage info
uv run indexed info
```

## MCP Server Usage

### Starting the Server

```bash
# Default: stdio transport (for Claude Desktop, Cline, etc.)
uv run indexed mcp

# HTTP server mode
uv run indexed mcp --transport http --port 8000

# With debug logging
uv run indexed mcp --log-level DEBUG

# With JSON logs for production
uv run indexed mcp --json-logs
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

### Cursor / Cline Configuration

Add to your MCP settings:

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

## Configuration

Configuration is managed via `config.toml` files with support for:
- Global config: `~/.indexed/config.toml`
- Local config: `./.indexed/config.toml` (overrides global)
- Environment variables: `INDEXED__<section>__<key>=value`
- `.env` file for sensitive credentials

### Example Configuration

```toml
[search]
max_docs = 10
max_chunks = 30
include_matched_chunks = true

[index]
embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
embedding_batch_size = 64

[sources.jira]
base_url = "https://company.atlassian.net"
email = "user@example.com"
# api_token is stored in .env file

[sources.confluence]
base_url = "https://company.atlassian.net/wiki"
email = "user@example.com"
# api_token is stored in .env file

[mcp]
log_level = "INFO"
mcp_json_output = true
```

### Environment Variables

**Required for Atlassian Cloud:**
- `ATLASSIAN_TOKEN` – API token for Jira/Confluence Cloud
- `ATLASSIAN_EMAIL` – Email for authentication

**Optional configuration:**
- `INDEXED__LOGGING__LEVEL` – Log level (DEBUG, INFO, WARNING, ERROR)
- `INDEXED__LOGGING__AS_JSON` – Enable JSON logging (true/false)
- `INDEXED__SEARCH__MAX_DOCS` – Default max documents per search
- `INDEXED__SEARCH__MAX_CHUNKS` – Default max chunks per search

## Design System

The CLI features a modern, card-based design system with:
- **Cyan accent color** (#2581C4) for emphasis
- **Card-based layout** for information display
- **Consistent info rows** with label-value pairs
- **Interactive spinners** with live status updates
- **Beautiful search results** with content previews
- **Responsive grid layouts** for multi-collection views

## Dependencies

| Package | Purpose |
|---------|---------|
| **indexed-core** | Core indexing and search engine |
| **indexed-config** | Configuration management |
| **indexed-connectors** | Document source connectors |
| **indexed-utils** | Shared utilities |
| **typer** | CLI framework |
| **rich** | Terminal output formatting |
| **fastmcp** | MCP server implementation |
| **art** | ASCII art for banner |

## Development

### Running Tests

```bash
# Run all CLI tests
uv run pytest tests/unit/indexed -v

# Run specific test file
uv run pytest tests/unit/indexed/mcp/test_server.py -v

# Run with coverage
uv run pytest tests/unit/indexed --cov=indexed
```

### Code Quality

```bash
# Format code
uv run ruff format indexed/

# Lint code
uv run ruff check indexed/

# Auto-fix linting issues
uv run ruff check indexed/ --fix
```

### Project Structure

```
indexed/
├── src/indexed/
│   ├── app.py                 # Main CLI application entry point
│   │
│   ├── knowledge/             # Index management commands
│   │   ├── cli.py            # Command group definition
│   │   └── commands/
│   │       ├── create.py     # Create collection command
│   │       ├── search.py     # Search command
│   │       ├── update.py     # Update command
│   │       ├── remove.py     # Remove command
│   │       └── inspect.py    # Inspect command
│   │
│   ├── config/               # Configuration commands
│   │   └── cli.py           # get, set, validate commands
│   │
│   ├── mcp/                  # MCP server
│   │   ├── cli.py           # MCP CLI entry point
│   │   └── server.py        # FastMCP server implementation
│   │
│   ├── info/                 # System info command
│   │   └── cli.py
│   │
│   ├── connectors/           # Connector CLI integration
│   │   └── __init__.py
│   │
│   └── utils/                # CLI utilities
│       ├── banner.py         # ASCII art banner
│       ├── console.py        # Shared Rich console
│       ├── logging.py        # Rich-enhanced logging
│       ├── credentials.py    # Credential prompting
│       ├── output_mode.py    # Output format handling
│       ├── progress_bar.py   # Progress indicators
│       └── components/       # Reusable Rich components
│           ├── theme.py      # Design system constants
│           ├── cards.py      # Card components
│           ├── info_row.py   # Info row component
│           ├── summary.py    # Summary components
│           ├── status.py     # Status spinner
│           └── alerts.py     # Alert messages
│
├── pyproject.toml
└── README.md                 # This file
```

## Entry Points

The package provides two main entry points defined in `pyproject.toml`:

| Entry Point | Module | Description |
|-------------|--------|-------------|
| `indexed` | `indexed.app:main` | Main CLI application |
| `indexed-mcp` | `indexed.mcp.cli:cli_main` | MCP server |

These are automatically installed when the package is installed via `uv`.

## License

See LICENSE file in the project root.
