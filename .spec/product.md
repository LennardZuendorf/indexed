---
type: entrypoint
scope: product
children: []
updated: 2026-06-15
---

# Product Spec: indexed

**indexed** is a privacy-first semantic search tool that indexes institutional knowledge (Jira, Confluence, local files) and makes it accessible to AI agents via MCP (Model Context Protocol).

**Core principle:** All processing happens locally. No data sent to third parties.

**Status:** v0.1.0 Alpha

> Roadmap and planned connectors/features are tracked in
> [GitHub issues](https://github.com/LennardZuendorf/indexed/issues), not here —
> this spec covers current focus only.

---

## Non-Goals

What indexed is **not**:
- Cloud service or SaaS platform
- Enterprise search replacement (targeting AI agent integration)
- Real-time collaboration search
- General-purpose database

---

## Features

### Indexing

| Feature | Status | Description |
|---------|--------|-------------|
| **File System** | ✅ Shipped | Index local files (.pdf, .docx, .pptx, .md, etc.) |
| **Jira Cloud** | ✅ Shipped | Index Jira Cloud issues with JQL filtering |
| **Jira Server/DC** | ✅ Shipped | Index on-premises Jira with JQL filtering |
| **Confluence Cloud** | ✅ Shipped | Index Confluence Cloud pages with CQL filtering |
| **Confluence Server/DC** | ✅ Shipped | Index on-premises Confluence with CQL filtering |
| **Outline Wiki** | ✅ Shipped | Index Outline docs + attachments (Cloud or self-hosted) |
| **Chunking** | ✅ Shipped | Split documents into searchable chunks (configurable size/overlap) |
| **Incremental Updates** | ✅ Shipped | Update collections without full re-index |
| **Batch Processing** | ✅ Shipped | Efficient batch embedding generation |

### Search

| Feature | Status | Description |
|---------|--------|-------------|
| **Semantic Search** | ✅ Shipped | Natural language queries via vector similarity |
| **Cross-Collection** | ✅ Shipped | Search across all collections simultaneously |
| **Single Collection** | ✅ Shipped | Target specific collection for focused results |
| **Relevance Scoring** | ✅ Shipped | FAISS L2 distance ranking (lower = closer match) |
| **Result Limits** | ✅ Shipped | Configurable max results per query |
| **Multiple Formats** | ✅ Shipped | Table, card, compact, JSON output |

### MCP Integration

| Feature | Status | Description |
|---------|--------|-------------|
| **Tools** | ✅ Shipped | `search`, `search_collection` |
| **Resources** | ✅ Shipped | Collection listing + per-collection status |
| **Stdio Transport** | ✅ Shipped | For Claude Desktop, Cline |
| **HTTP Transport** | ✅ Shipped | Network-accessible server |
| **SSE Transport** | ✅ Shipped | Server-Sent Events streaming |
| **Error Handling** | ✅ Shipped | Rich error messages with context |

### CLI

| Feature | Status | Description |
|---------|--------|-------------|
| **Create Collections** | ✅ Shipped | `indexed index create` |
| **Search** | ✅ Shipped | `indexed index search` |
| **Update** | ✅ Shipped | `indexed index update` |
| **Inspect** | ✅ Shipped | `indexed index inspect` |
| **Remove** | ✅ Shipped | `indexed index remove` |
| **Config Management** | ✅ Shipped | `inspect`, `set`, `validate` commands |
| **System Info** | ✅ Shipped | `indexed info` |
| Progress Indicators | ⚠️ Partial | Spinners exist, bars planned |

### Configuration

| Feature | Status | Description |
|---------|--------|-------------|
| **TOML Config** | ✅ Shipped | Human-readable config files |
| **Environment Vars** | ✅ Shipped | `INDEXED__*` override system |
| **Credential Management** | ✅ Shipped | Separate .env for secrets |
| **Global/Local Modes** | ✅ Shipped | System-wide or per-project collections |
| **Validation** | ✅ Shipped | Pydantic schema validation |
| **Single-Source Config** | ✅ Shipped | Resolves to one config.toml (no global+local merge) |
| **CWD/.env Support** | ✅ Shipped | Project-level .env loaded as credential fallback |
| **.gitignore Protection** | ✅ Shipped | Local .indexed/ auto-creates .gitignore with .env entry |

---

## Deployment Modes

### Local (Primary)

**What:** Run indexed on developer workstation
**Why:** Privacy, offline access, zero ops overhead
**Storage:** `~/.indexed/` (global) or `./.indexed/` (local)

### Docker

**What:** Containerized deployment
**Why:** Isolated environment, reproducible builds
**Status:** ✅ Shipped (Dockerfile + compose)

---

## UX Principles

### Privacy First

- Never send data externally
- All embedding generation local
- Credentials stored in .env (not config)
- No telemetry or analytics

### Fast & Minimal

- CLI startup <1s despite ML dependencies
- Search latency <1s for typical collections
- Minimal configuration required
- Sensible defaults

### Developer Experience

- Beautiful terminal output (Rich)
- Guided prompts for setup
- Clear error messages
- Excellent documentation

### Composability

- Unix philosophy (do one thing well)
- JSON output for scripting
- Standard protocols (MCP)
- Extensible connector system

---

## Output Formats

| Format | Use Case | Example |
|--------|----------|---------|
| **Card** | Rich terminal display | Default for `search` |
| **Table** | Structured comparison | `inspect` collections |
| **Compact** | Quick scanning | Titles only |
| **JSON** | Scripting/piping | `--json` flag |

---

## User Flows

### First-Time Setup

1. Install: `uv sync`
2. Verify: `uv run indexed --help`
3. Create first collection: `indexed index create my-docs --source files --source-path ./docs`
4. Search: `indexed index search "query"`

**Critical:** This must work in <5 minutes.

### Adding MCP to Claude Desktop

1. Create collections (above)
2. Edit `claude_desktop_config.json`
3. Add indexed MCP server config
4. Restart Claude Desktop
5. Ask Claude to search collections

**Critical:** Clear instructions, no debugging needed.

### Daily Developer Workflow

1. Search from terminal: `indexed index search "query"`
2. Or use Claude Desktop with MCP integration
3. Periodically update: `indexed index update collection-name`

**Critical:** Fast, no friction, always available.

---

## Open Questions

1. **Multi-user collections** — How should permissions work in server mode? Per-collection ACLs? Role-based?

2. **Embedding model updates** — What's the migration path when updating models? Automatic re-index? Versioning strategy?

3. **Real-time updates** — Should collections auto-update when source data changes? Webhook integration? Polling?

4. **Cloud offering** — Is there demand for optional hosted service? Conflicts with privacy-first positioning but may serve different market.

5. **Licensing** — What license best serves community adoption while enabling sustainable development?
