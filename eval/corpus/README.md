<div align="center">

<img src="./docs/img/logo.png" alt="Indexed Logo" width="500"/>

### One local knowledge base per project. Code, docs, issues, wikis — one MCP, zero cloud.

[![License: Sustainable Use](https://img.shields.io/badge/License-Sustainable%20Use-blue)](#license)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](#)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-5A45FF)](#mcp-integration)

[![Python Full Test Suite with Coverage](https://github.com/LennardZuendorf/indexed/actions/workflows/python-cov.yml/badge.svg)](https://github.com/LennardZuendorf/indexed/actions/workflows/python-cov.yml) [![Python Build and System Tests](https://github.com/LennardZuendorf/indexed/actions/workflows/python-ci.yml/badge.svg)](https://github.com/LennardZuendorf/indexed/actions/workflows/python-ci.yml) [![Python Performance Benchmarks](https://github.com/LennardZuendorf/indexed/actions/workflows/python-benchmark.yml/badge.svg)](https://github.com/LennardZuendorf/indexed/actions/workflows/python-benchmark.yml) [![codecov](https://codecov.io/gh/LennardZuendorf/indexed/graph/badge.svg?token=6P99FW1Z1A)](https://codecov.io/gh/LennardZuendorf/indexed)

[Quickstart](#quick-start) · [Documentation](https://indexed.sh/docs) · [Blog & Guides](https://indexed.sh/blog)

</div>

---

Local-first semantic search for AI agents. Give Claude Code, Cursor, Codex, and other MCP-compatible agents deep context over your codebase, docs, issues, and wikis — no source read in isolation.

**Key Features:**
- **Privacy-first** — all processing and storage happens locally, no data sent to third parties
- **Semantic search** — understands meaning, not just keywords, using a LlamaIndex-powered engine with optional cross-encoder reranking
- **Multiple sources** — local files (25+ formats), Jira, Confluence, Outline Wiki, and GitHub (issues, PRs, Projects v2)
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

- **Not just search.** A single index over one source is the easy part — every RAG toolkit does that. The hard, useful part is that no single source has the answer: code doesn't explain *why*, a ticket doesn't show *what shipped*, history doesn't say *if it's still true*. Indexed's direction is one merged knowledge base per project — code, docs, issues, and wikis tied together, not five indexes you query separately. See [`.spec/product.md`](.spec/product.md) § Vision for where this is headed (structural graph relationships, graph-aware retrieval, optional local-model-driven merging).
- **Not just code.** Index Markdown, PDFs, DOCX, PPTX, images, and 25+ formats via Docling. AST-aware code chunking via tree-sitter.
- **Not just local files.** Native Jira, Confluence, Outline Wiki, and GitHub connectors pull tickets, pages, issues, and PRs into your index.
- **Not cloud-dependent.** Runs entirely on your machine. Local embedding models, FAISS or LlamaIndex-managed vector storage. No API keys required.
- **Not one-shot.** Incremental updates via `indexed index update` keep your index fresh as your sources evolve.

## MCP Integration

Indexed exposes a Model Context Protocol server for AI agent integration.

### Claude Code (CLI, VS Code, JetBrains)

Works across all Claude Code surfaces — CLI, VS Code extension, and JetBrains plugin:

```bash
claude mcp add indexed -- indexed mcp run
```

This adds indexed to your project's `.mcp.json`. You can also manage servers via `/mcp` in the VS Code chat panel.

To add manually, create or edit `.mcp.json` in your project root:

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
| **Outline Wiki** | Cloud or self-hosted, with attachments and OCR |
| **GitHub** | Issues, PR threads, and Projects v2 boards — github.com, GHE, or self-hosted GHES |

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
# Create collections (Jira/Confluence auto-detect Cloud vs Server from --url)
indexed index create files --collection my-project --path ./src
indexed index create jira --collection jira-issues --url https://your-domain.atlassian.net
indexed index create confluence --collection wiki --url https://your-domain.atlassian.net/wiki
indexed index create outline --collection docs
indexed index create github --collection my-repo --repo owner/repo
indexed index create files --collection my-app --path ./src --engine v2

# Search
indexed index search "authentication flow"
indexed index search "bug reports" --collection jira-issues
indexed index search "why was this refactored" --rerank   # v2 collections only

# Manage collections
indexed index inspect                    # list all collections
indexed index inspect my-project         # inspect specific collection
indexed index update my-project          # update a collection
indexed index remove my-project          # delete a collection
indexed index migrate my-project         # migrate to the v2 engine

# Configuration
indexed config inspect                   # view config
indexed config set search.max_docs 20    # set a value
```

For the full CLI reference and configuration guide, see the [documentation](https://indexed.sh/docs).

## Roadmap

Indexed today runs parallel semantic indexes per source. The direction is one merged
knowledge graph per project — code, docs, issues, git history, connected codebases, and
accumulated lessons/memory as one structure instead of several. See
[`.spec/product.md`](.spec/product.md) § Vision and § Knowledge Graph for what's shipped
vs. planned.

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

Performance benchmarks (`tests/benchmarks/`, `tests/system/`) run in CI via
[`pytest-bench-action`](https://github.com/LennardZuendorf/pytest-bench-action)
— see `.github/workflows/python-benchmark.yml`. Run them locally with:

```bash
uv run pytest tests/system tests/benchmarks --benchmark-only
```

See [`AGENTS.md`](AGENTS.md) and [`.spec/tech.md`](.spec/tech.md) for architecture details.

## License

See [LICENSE](./LICENSE) file for details.

## Credits

The Core v1 implementation is based on [documents-vector-search](https://github.com/shnax0210/documents-vector-search) by shnax0210, licensed under MIT and modified extensively.

---

**[indexed.sh](https://indexed.sh)** · Star the repo if you find it useful!
