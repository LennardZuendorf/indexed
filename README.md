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

Local-first semantic search for AI agents. Give Claude Code, Cursor, Codex, and other MCP-compatible agents deep context over your codebase, docs, Jira, and Confluence.

**Key Features:**
- **Privacy-first** — all processing and storage happens locally, no data sent to third parties
- **Semantic search** — understands meaning, not just keywords, using dense vector embeddings
- **Multiple sources** — index local files (25+ formats), Jira, and Confluence (Cloud & Server)
- **MCP integration** — works with Claude Code, Cursor, Windsurf, Cline, and other MCP-compatible agents
- **Incremental updates** — keep your index fresh with git-based change tracking

## Quick Start

```bash
# 1. Install indexed globally
uv tool install indexed-sh

# 2. Create a collection from local files
indexed index create files --collection my-project --path ./src

# 3. Search your collection
indexed index search "your query"
```

## Why Indexed?

AI agents search your codebase on demand with grep — fast for small repos, but expensive on large ones. Every file read costs tokens. Every broad search burns context window.

Indexed pre-computes a semantic search index over your code, docs, and project tools, then exposes it via MCP. The result: instant, relevant context retrieval without the token overhead.

- **Not just code.** Index Markdown, PDFs, DOCX, PPTX, images, and 25+ formats via Docling. AST-aware code chunking via tree-sitter.
- **Not just local files.** Native Jira and Confluence connectors pull tickets, pages, and metadata into your index.
- **Not cloud-dependent.** Runs entirely on your machine. Local embedding models, FAISS for vector storage. No API keys required.
- **Not one-shot.** Incremental updates via `indexed index update` keep your index fresh as your codebase evolves.

## MCP Integration

Indexed exposes a Model Context Protocol server for AI agent integration.

### Claude Code

```bash
claude mcp add indexed -- indexed mcp run
```

Or add manually to your `.mcp.json`:

```json
{
  "mcpServers": {
    "indexed": {
      "command": "indexed",
      "args": ["mcp", "run"]
    }
  }
}
```

### Cursor / Windsurf / Other Agents

Add to your agent's MCP configuration file:

```json
{
  "mcpServers": {
    "indexed": {
      "command": "indexed",
      "args": ["mcp", "run"]
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "indexed": {
      "command": "indexed",
      "args": ["mcp", "run"]
    }
  }
}
```

### Server Mode

```bash
# HTTP server mode
indexed mcp run --transport http --port 8000
```

## Supported Sources

| Source | Description |
|--------|-------------|
| **Local Files** | `.pdf`, `.docx`, `.pptx`, `.md`, code files, images, and 25+ formats |
| **Jira** | Cloud and Server/Data Center with JQL filtering |
| **Confluence** | Cloud and Server/Data Center with CQL filtering |

## Installation

Requires **Python 3.11+** and **[uv](https://docs.astral.sh/uv/)**.

```bash
uv tool install indexed-sh
```

This installs `indexed` as a global CLI tool from [PyPI](https://pypi.org/project/indexed-sh/).

<details>
<summary>Alternative: run without installing</summary>

```bash
uvx indexed-sh index search "your query"
```

</details>

<details>
<summary>Alternative: install from source</summary>

```bash
git clone https://github.com/LennardZuendorf/indexed.git
cd indexed
uv sync
uv run indexed --help
```

</details>

## Usage

```bash
# Create collections
indexed index create files --collection my-project --path ./src
indexed index create jiraCloud --collection jira-issues
indexed index create confluenceCloud --collection wiki

# Search
indexed index search "authentication flow"
indexed index search "bug reports" --collection jira-issues

# Manage collections
indexed index inspect                    # list all collections
indexed index inspect my-project         # inspect specific collection
indexed index update my-project          # update a collection
indexed index remove my-project          # delete a collection

# Configuration
indexed config inspect                   # view config
indexed config set search.max_docs 20    # set a value
```

For the full CLI reference and configuration guide, see the [documentation](https://indexed.sh/docs).

## Documentation

- [Full Documentation](https://indexed.sh/docs) — CLI reference, configuration, and guides
- [Blog & Guides](https://indexed.sh/blog) — tutorials and use cases
- [Issue Tracker](https://github.com/LennardZuendorf/indexed/issues) — report bugs or request features

## Contributing

```bash
git clone https://github.com/LennardZuendorf/indexed.git
cd indexed
uv sync --all-groups
uv run pytest -q
```

See the internal package docs and `CLAUDE.md` for architecture details.

## License

See [LICENSE](./LICENSE) file for details.

## Credits

The Core v1 implementation is based on [documents-vector-search](https://github.com/shnax0210/documents-vector-search) by shnax0210, licensed under MIT and modified extensively.

---

**[indexed.sh](https://indexed.sh)** · Star the repo if you find it useful!
