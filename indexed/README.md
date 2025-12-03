# indexed

Command-line interface and MCP server for semantic document search with AI agent integration.

## Overview

`indexed` provides a powerful CLI and MCP (Model Context Protocol) server for creating, managing, and searching document collections using semantic similarity. It enables AI agents and LLMs to access institutional knowledge from various sources including Jira, Confluence, and local files.

## Features

### CLI Commands

- **create** - Create document collections from various sources
  - `jira` - Index Jira issues (Cloud and Server/DC)
  - `confluence` - Index Confluence pages (Cloud and Server/DC)
  - `files` - Index local files and directories

- **search** - Semantic search across collections with beautiful card-based results
- **update** - Update existing collections with latest data
- **delete** - Remove collections with confirmation
- **inspect** - View collection metadata, statistics, and status
- **config** - Manage configuration (get, set, validate)
- **mcp** - Start MCP server for AI agent integration

### MCP Server

FastMCP-based server providing tools and resources for AI agents:

**Tools:**
- `search` - Search across all collections
- `search_collection` - Search within a specific collection

**Resources:**
- `resource://collections` - List of available collection names
- `resource://collections/status` - Detailed status for all collections
- `resource://collections/{name}` - Detailed status for specific collection

**Transport Modes:**
- `stdio` - Standard I/O for Claude Desktop, Cline, etc. (default)
- `http` - HTTP server mode
- `sse` - Server-Sent Events mode
- `streamable-http` - Streamable HTTP mode

## Installation

This package is part of the indexed monorepo workspace. Use `uv` for dependency management:

```bash
# Install all dependencies including development tools
uv sync --all-groups

# Install production dependencies only
uv sync
```

## Usage

### CLI Examples

```bash
# Create a collection from Jira Cloud
uv run indexed-cli create jira \
  -c my-issues \
  -u https://company.atlassian.net \
  --jql "project = PROJ AND created >= -30d"

# Create a collection from Confluence Cloud
uv run indexed-cli create confluence \
  -c wiki \
  -u https://company.atlassian.net/wiki \
  --cql "space = DEV"

# Create a collection from local files
uv run indexed-cli create files \
  -c docs \
  --basePath ./documents \
  --includePatterns ".*\.md$" ".*\.txt$"

# Search across all collections
uv run indexed-cli search "authentication methods"

# Search specific collection
uv run indexed-cli search "bug reports" -c my-issues

# Search with compact output
uv run indexed-cli search "API documentation" --compact

# Inspect all collections
uv run indexed-cli inspect

# Inspect specific collection
uv run indexed-cli inspect my-issues

# Update a collection
uv run indexed-cli update my-issues

# Delete a collection
uv run indexed-cli delete my-issues

# View configuration
uv run indexed-cli config get all

# Set configuration value
uv run indexed-cli config set search.max_docs 20

# Validate configuration
uv run indexed-cli config validate
```

### MCP Server Examples

```bash
# Start MCP server with stdio (for Claude Desktop)
uv run indexed-mcp

# Start HTTP server
uv run indexed-mcp --transport http --port 8000

# Start with debug logging
uv run indexed-mcp --log-level DEBUG

# Start with JSON logs for production
uv run indexed-mcp --json-logs
```

### Using with Claude Desktop

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "indexed": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/indexed-python",
        "run",
        "indexed-mcp"
      ]
    }
  }
}
```

### Using with Cline (VS Code)

Add to your Cline MCP settings:

```json
{
  "mcpServers": {
    "indexed": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/indexed-python",
        "run",
        "indexed-mcp"
      ]
    }
  }
}
```

## Configuration

Configuration is managed via `indexed.toml` in the project root, with support for:
- Environment variables (prefix: `INDEXED__`)
- `.env` file
- Configuration profiles
- Runtime overrides

### Example Configuration

```toml
[paths]
collections_dir = "./data/collections"
caches_dir = "./data/caches"

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
api_token_env = "JIRA_API_TOKEN"

[sources.confluence]
base_url = "https://company.atlassian.net/wiki"
email = "user@example.com"
api_token_env = "CONFLUENCE_API_TOKEN"

[mcp]
log_level = "INFO"
mcp_json_output = true
```

### Environment Variables

Required for Atlassian Cloud integration:
- `JIRA_API_TOKEN` - Jira Cloud API token
- `CONFLUENCE_API_TOKEN` - Confluence Cloud API token

Optional configuration:
- `INDEXED__LOGGING__LEVEL` - Log level (DEBUG, INFO, WARNING, ERROR)
- `INDEXED__LOGGING__AS_JSON` - Enable JSON logging (true/false)
- `INDEXED__SEARCH__MAX_DOCS` - Default max documents per search
- `INDEXED__SEARCH__MAX_CHUNKS` - Default max chunks per search

## Design System

The CLI features a modern, card-based design system with:
- **Cyan accent color** (#2581C4) for emphasis
- **Card-based layout** for information display
- **Consistent info rows** with label-value pairs
- **Interactive spinners** with live status updates
- **Beautiful search results** with content previews
- **Responsive grid layouts** for multi-collection views

## Dependencies

- **indexed-core** - Core indexing and search engine
- **indexed-utils** - Shared utilities
- **typer** - CLI framework with rich help formatting
- **rich** - Beautiful terminal output
- **fastmcp** - MCP server implementation
- **art** - ASCII art for banner

## Development

### Running Tests

```bash
# Run all CLI tests
uv run pytest tests/cli -v

# Run specific test file
uv run pytest tests/cli/test_app.py -v

# Run with coverage
uv run pytest tests/cli --cov=cli
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
├── src/cli/
│   ├── app.py              # Main CLI application
│   ├── mcp.py              # MCP server implementation
│   ├── commands/           # CLI command modules
│   │   ├── create.py       # Create command
│   │   ├── search.py       # Search command
│   │   ├── update.py       # Update command
│   │   ├── delete.py       # Delete command
│   │   ├── inspect.py      # Inspect command
│   │   └── config.py       # Config command
│   ├── components/         # Reusable Rich components
│   │   ├── theme.py        # Design system constants
│   │   ├── cards.py        # Card components
│   │   ├── info_row.py     # Info row component
│   │   ├── summary.py      # Summary components
│   │   └── status.py       # Status spinner component
│   ├── formatters/         # Output formatters
│   │   ├── search_formatter.py
│   │   ├── inspect_formatter.py
│   │   ├── update_formatter.py
│   │   └── delete_formatter.py
│   └── utils/              # CLI utilities
│       ├── banner.py       # ASCII art banner
│       ├── console.py      # Shared console instance
│       └── config_format.py # Config formatting
└── README.md
```

## Entry Points

The package provides two main entry points:

- `indexed-cli` - Main CLI application (`cli.app:main`)
- `indexed-mcp` - MCP server (`cli.mcp:main`)

These are automatically installed when the package is installed via `uv`.

## License

See LICENSE file in the project root.
