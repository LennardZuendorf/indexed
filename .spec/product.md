---
type: entrypoint
scope: product
children: [product-readiness.md]
updated: 2026-11-21
---

# Product Spec: indexed

Indexed gives developers and agents searchable project context across code,
documentation, issues and other development evidence. Indexing and ranking run
locally. Connectors fetch configured sources, and model preparation downloads the
files needed for local inference.

**Status:** [Alpha v0.0.11](https://github.com/LennardZuendorf/indexed/releases/tag/v0.0.11)

---

## Vision

A developer can ask why code exists, find the issue or wiki page that explains
it, and follow the result to the relevant symbol or change. Developers and
agents in the same project search the same repository-selected collections.
Multiple projects can use the same index data.

The current release searches local files, Jira, Confluence, Outline and GitHub
through CLI and MCP. It includes Git provenance, local watching, editor
navigation and a Claude Code installer.

The readiness target is shared global collections with a repo definition,
measured merged search over GitHub issues, a local Markdown wiki and code,
searchable Git history and development sources, code graph traversal, a full
language server for supported languages, and plugin setup across the target
agent clients. Clear documentation and product copy make these workflows
usable from a clean install. See the [readiness product requirements](product-readiness.md)
for user workflows and acceptance criteria, and the [plan](plan.md#readiness-milestones)
for baseline coverage, issue ownership and sequence.

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
| **GitHub Issues/PRs/Projects** | ✅ Shipped | Index issues, PRs and Projects v2 items with bounded conversation and field coverage |
| Google Drive | 📋 Planned | Index Google Docs, Sheets, Slides |
| Notion | 📋 Planned | Index Notion pages and databases |
| Slack | 📋 Planned | Index Slack messages and threads |

### Knowledge Graph

Direction, not yet shipped — see § Vision above.

| Feature | Status | Description |
|---------|--------|-------------|
| Structural graph edges | 📋 Planned | Relationships derived from existing source structure — no LLM required (doc→chunk hierarchy, code imports, issue/PR links, commit→file) |
| Graph-aware retrieval | 📋 Planned | Follow a search hit to its linked nodes, alongside vector search — not a replacement for it |
| Cross-source merge | 📋 Planned | Unify multiple collections (code, docs, issues, git history, connected repos, lessons) into one graph per project |
| Local-model-driven merging | 📋 Planned | Optional richer entity/relation extraction via a local model (e.g. Ollama) — additive on top of the structural graph, never required |

### Search

| Feature | Status | Description |
|---------|--------|-------------|
| **Semantic Search** | ✅ Shipped | Natural language queries via vector similarity |
| **Cross-Collection** | ✅ Shipped | Search across all collections simultaneously |
| **Single Collection** | ✅ Shipped | Target specific collection for focused results |
| **Relevance Scoring** | ✅ Shipped | Comparable relevance alongside the original score and its kind |
| **Result Limits** | ✅ Shipped | Configurable max results per query |
| **Multiple Formats** | ✅ Shipped | Table, card, compact, JSON output |
| **Reranking (v2)** | ✅ Shipped | Optional cross-encoder for v2 collections. Prepare the separate reranker model for offline use. |
| **Git-aware search** | ✅ Shipped | Changed-since filtering, provenance, line blame, freshness and optional Git-signal ranking |
| Filters | 📋 Planned | Filter by date, source type, metadata |
| Boolean Operators | 📋 Planned | AND, OR, NOT query composition |
| Phrase Search | 📋 Planned | Exact phrase matching |

### MCP Integration

| Feature | Status | Description |
|---------|--------|-------------|
| **Tools** | ✅ Shipped | `search` and `search_collection` |
| **Resources** | ✅ Shipped | Collection listings and status endpoints |
| **Stdio Transport** | ✅ Shipped | For Claude Desktop, Cline |
| **HTTP Transport** | ✅ Shipped | Network-accessible server |
| **SSE Transport** | ✅ Shipped | Server-Sent Events streaming |
| **Error Handling** | ✅ Shipped | Rich error messages with context |
| Streaming Results | 📋 Planned | Progressive result delivery |
| Subscriptions | 📋 Planned | Real-time collection updates |

### CLI

| Feature | Status | Description |
|---------|--------|-------------|
| **Create Collections** | ✅ Shipped | `indexed index create` |
| **Search** | ✅ Shipped | `indexed index search` |
| **Update** | ✅ Shipped | `indexed index update` |
| **Inspect** | ✅ Shipped | `indexed index inspect` |
| **Remove** | ✅ Shipped | `indexed index remove` |
| **Config Management** | ✅ Shipped | `get`, `set`, `validate` commands |
| **System Info** | ✅ Shipped | `indexed info` and `indexed --version` |
| **Local watching** | ✅ Shipped | Foreground CLI watcher and opt-in MCP watching for eligible collections present at startup |
| **Editor navigation** | ✅ Shipped | `indexed lsp` provides workspace symbols, hover, bounded definition and references, and informational diagnostics |
| **Claude Code setup** | ✅ Shipped | `indexed install claude-code` registers MCP and installs the `index-use` skill |
| **Engine Selection** | ✅ Shipped | `--engine v1/v2` on `index create` (root, group, and leaf flags) — new collections only |
| **Migrate to v2** | ✅ Shipped | `indexed index migrate` — dry-run/backup/rollback-safe v1→v2 conversion |
| Interactive TUI | 📋 Planned | Full-screen interactive mode |
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
| Config Profiles | 📋 Planned | Named config sets (dev, prod, etc.) |

---

## Deployment Modes

### Local (Primary)

**What:** Run indexed on developer workstation
**Why:** Privacy, offline access, zero ops overhead
**Storage:** `~/.indexed/` (global) or `./.indexed/` (local)

### Server (Future)

**What:** Dedicated server for team access
**Why:** Centralized collections, shared indexes
**Status:** 📋 Planned (HTTP API + auth)

---

## UX Principles

### Privacy First

- Keep indexing, embedding and ranking local
- Fetch configured remote sources and requested model files
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

1. Install with `uv tool install indexed-sh`.
2. Prepare the default model with `indexed init`.
3. Create a collection with `indexed index create files --collection docs --path ./docs`.
4. Run `indexed index search "query"`.

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

3. **Remote source freshness** — What update cadence or change signals should remote connectors support?

4. **Cloud offering** — Is there demand for optional hosted service? Conflicts with privacy-first positioning but may serve different market.

5. **Licensing** — What license best serves community adoption while enabling sustainable development?
