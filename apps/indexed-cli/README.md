# indexed-cli

Command-line interface and MCP server for the indexed document search system.

## Features

### CLI Commands

- **create** - Create document collections from various sources (Jira, Confluence, local files)
- **search** - Semantic search across collections
- **update** - Update existing collections with latest data
- **delete** - Remove collections
- **inspect** - View collection metadata and statistics
- **config** - Manage configuration (get, set, validate)

### MCP Server

FastMCP-based server providing:
- Search tools for AI agents
- Collection inspection resources
- Configurable via environment variables

## Installation

```bash
uv sync --all-groups
```

## Usage

```bash
# Create a collection
uv run indexed-cli create jira -c my-issues -u https://company.atlassian.net --jql "project = PROJ"

# Search
uv run indexed-cli search "authentication methods" -c api-docs

# Start MCP server
uv run indexed-mcp
```
