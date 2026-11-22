<div align="center">

<img src="./docs/img/logo.png" alt="Indexed Logo" width="500"/>

### One local knowledge base per project. Code, docs, issues, wikis — one MCP, zero cloud.

[![License: Sustainable Use](https://img.shields.io/badge/License-Sustainable%20Use-blue)](#license)
[![Python 3.11–3.14](https://img.shields.io/badge/Python-3.11%E2%80%933.14-3776AB?logo=python&logoColor=white)](#)
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
- **LSP integration** — `indexed lsp` serves the same index to any editor: search it from the symbol palette, hover a file to see what the index knows, jump to the definition the index has seen, list the places it has seen a name, and get diagnostics that say only what the index can prove — this file is not in any collection, or the index holds an older version of it (VS Code, Neovim, Zed, Helix)
- **Incremental updates** — keep your index fresh with git-based change tracking

## Quick Start

```bash
# 1. Install indexed globally
uv tool install indexed-sh

# 2. One-time setup: fetch the embedding model
indexed init

# 3. Create a collection from local files
indexed index create files --collection my-project --path ./src

# 4. Search your collection
indexed index search "your query"

# 5. Or take the machine payload (the MCP tools return the same object)
indexed index search "your query" --json
```

**What the first run downloads.** Indexed fetches the embedding model
`sentence-transformers/all-MiniLM-L6-v2` — about 88 MB of weights and tokenizer —
into the HuggingFace cache (`~/.cache/huggingface`, override with `HF_HOME`).
Skipping `indexed init` only moves that download into the first `index create`;
after that every command reads from the cache and works offline
(`HF_HUB_OFFLINE=1`).

On success, `--json` prints one object with a `schema` id, documents grouped, and
a locator per hit. Check the CLI exit code before parsing stdout; escaping errors
can print a non-JSON error panel, and exit 0 can still contain an error body.
This excerpt keeps values from a real collection; the second hit is elided,
which is why `counts.hits` says 2:

```json
{
  "schema": "indexed.search/1",
  "query": "how are failed requests retried",
  "counts": { "documents": 1, "hits": 2 },
  "collections": ["docs-quick"],
  "collection_errors": [],
  "documents": [
    {
      "collection": "docs-quick",
      "source_type": "localFiles",
      "id": "retry.md",
      "url": "file:///tmp/indexed-docs-quick/retry.md",
      "score_kind": "l2_squared",
      "hits": [
        {
          "relevance": 0.6003,
          "score": 0.7995,
          "locator": { "kind": "headings", "headings": ["Retry policy"] },
          "text": "Retry policy\nRequests are retried three times with exponential backoff. A 429 response resets the backoff window instead of failing the call."
        }
      ]
    }
  ]
}
```

Full field list: [`docs/reference/search-output.md`](docs/reference/search-output.md).

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

Works across all Claude Code surfaces — CLI, VS Code extension, and JetBrains plugin.
One command registers the MCP server, installs the `index-use` skill and adds a
`PreToolUse` hook that nudges Claude away from Grep/Glob toward semantic search:

```bash
indexed install claude-code             # server + skill + hook
indexed install claude-code --dry-run   # print the plan, write nothing
indexed install claude-code --remove    # undo exactly what it installed
indexed install claude-code --home /data/agent-home  # collections in /data/agent-home/.indexed
```

It writes a *user-scope* server (available in every project) using the absolute
path of the running `indexed` executable, and touches four files:

| Path | What it owns |
| --- | --- |
| `~/.claude.json` | the `mcpServers.indexed` entry |
| `~/.claude/skills/index-use/SKILL.md` | the `index-use` skill |
| `~/.claude/hooks/indexed-suggest-mcp.sh` | the nudge hook script |
| `~/.claude/settings.json` | the `PreToolUse` group that runs that hook |

Everything else in those files — other servers, other hooks, `projects`,
credentials — is preserved, and each rewritten file keeps a `.bak` beside it.
Safe to run twice: an existing install is upgraded in place, never duplicated.
`--remove` deletes only the artifacts above (and only ones it recognises as its
own) and prunes the directories it emptied.

The hook is silent unless indexed actually has collections (the collections root
this install points at, or a `.indexed/collections.json` workspace pointer), so it
costs nothing on a machine that does not use indexed. It only *adds context* to
Grep/Glob calls — it never approves, blocks or prompts, so your permission rules
and directory prompts behave exactly as before. Set
`INDEXED_HOOK_LOG=/path/to/log` to trace its firings.

Restart Claude Code, then use `/index-use`.

Manual alternative (registers the server only — no skill, no hook):

```bash
claude mcp add indexed -s user -- indexed mcp run
```

To add it per project instead, create or edit `.mcp.json` in your project root:

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

The installed skill documents the `indexed.search/1` result shape; the full
contract is in [docs/reference/search-output.md](docs/reference/search-output.md).

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

### Keeping an MCP server fresh

An MCP server is long-lived, so there is no per-collection command to run. Turn the
[`index watch`](#watching-a-collection) watcher on for the server with an opt-in switch
(**off by default** — nothing changes if you don't set it):

```toml
[mcp]
watch_enabled = true
watch_debounce_seconds = 2.0
watch_poll_interval_seconds = 2.0
```

With it on, `indexed-mcp run` plans a watcher for **every `localFiles` collection that exists
at startup**: an edit, new file or deletion shows up in `search` within roughly one poll
(`watch_poll_interval_seconds`), one quiet period (`watch_debounce_seconds`) and the update
pass itself — with no manual `index update` and no server restart. A startup catch-up pass
also indexes edits made while the collection was not watched.

The watched set is fixed at startup: a collection created *while the server is running* is
not watched, and is picked up on the next restart — the set is never re-planned behind you.
Remote collections (Jira, Confluence, Outline, GitHub) are never watched: only local files
have a change signal.

Its cost is one background thread per watched collection, held for the lifetime of the
server. Those threads come from the event loop's default pool, which is capped at
`min(32, CPU count + 4)`: collections past that cap wait without refreshing instead of
starting. A watcher that fails three update passes in a row also stops for that collection —
the server keeps serving the last good index, and only a restart starts it again. Same
caveats as the CLI: the server is a single writer per collection, and a source directory that
disappears keeps the last good index rather than emptying the collection.

## Supported Sources

| Source | Description |
|--------|-------------|
| **Local Files** | `.pdf`, `.docx`, `.pptx`, `.md`, code files, images, and 25+ formats |
| **Jira** | Cloud and Server/Data Center with JQL filtering |
| **Confluence** | Cloud and Server/Data Center with CQL filtering |
| **Outline Wiki** | Cloud or self-hosted, with attachments and OCR |
| **GitHub** | Issues, PR threads, and Projects v2 boards — github.com, GHE, or self-hosted GHES |

## Installation

Requires **Python 3.11–3.14** and **[uv](https://docs.astral.sh/uv/)**. The upper
bound is temporary: `onnxruntime` publishes no `cp315` wheel yet, so a 3.15
interpreter cannot resolve the dependency set.

```bash
uv tool install indexed-sh
```

This installs `indexed` as a global CLI tool from [PyPI](https://pypi.org/project/indexed-sh/).

```bash
indexed --version   # prints the installed version, e.g. 0.0.11
```

Then run the one-time setup, which creates `~/.indexed`, validates your config,
and fetches the default embedding model into the HuggingFace cache:

```bash
indexed init
```

`indexed init` fetches only the files the embedder loads — the safetensors
weights, the tokenizer, and the configs the sentence-transformers modules read —
about 88 MB on a clean cache. It does not fetch the repository's other exports
(ONNX, OpenVINO, TF, the torch `.bin`), so setup stays bounded to the model files
that loading actually reads. It is idempotent.

Skipping it is safe, and it defers nothing beyond that download: the first
`index create` fetches the same ~88 MB at that moment instead. Neither path ever
pulls the whole repository, and after that one download every command reads the
cache and works offline.

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
# Setup
indexed init                              # one-time model fetch (~88 MB) + data dirs

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
indexed index search "authentication flow" --json        # indexed.search/1 payload
indexed index search "recent work" --changed-since HEAD~5  # v2 files collections
indexed index search "who wrote this" --git-provenance     # v2 files collections only
indexed index search "who wrote these lines" --git-line-blame  # v2 files collections only
indexed index search "what changed lately" --git-rerank    # v2 files collections only
indexed index search "auth" --freshness                    # warn if the index is behind
# A filter a collection cannot honour warns per collection, never silently

# Manage collections
indexed index inspect                    # list all collections
indexed index inspect my-project         # inspect specific collection (+ freshness)
indexed index update my-project          # update a collection
indexed index remove my-project          # delete a collection
indexed index migrate my-project         # migrate to the v2 engine

# Keep a collection fresh while you work (opt-in, foreground)
indexed index watch my-project           # Ctrl-C to stop
indexed index watch my-project --debounce 5 --poll-interval 1

# Configuration
indexed config list                              # resolved configuration
indexed config set core.v1.search.max_docs 20    # set a value

# Share one collection between projects (stable id in ~/.indexed)
indexed storage migrate --dry-run         # report collisions and affected data
indexed storage migrate                   # move this project's collections to the shared store
indexed storage migrate --on-collision adopt  # reuse an identical copy instead of keeping a second
indexed storage migrate --rollback        # put this project's collections back

# Editor integration (Language Server Protocol, stdio)
indexed lsp                              # point your editor's LSP client here
```

`indexed storage migrate` gives a collection a stable id in the global store and
leaves a pointer in `./.indexed/collections.json`, so a second project reads the
same index instead of rebuilding it. It journals every step, so an interrupted
run resumes where it stopped, and `--rollback` restores the original local
collection.

For the full CLI reference and configuration guide, see the [documentation](https://indexed.sh/docs).

### Editor setup (LSP)

`indexed lsp` is a stdio server over the **same storage as the CLI**. Start it from the
project root; a workspace `.indexed` store needs `indexed --local lsp`. VS Code has no
built-in hook, so register the command in a generic LSP client extension's `settings.json`:
`{"indexed": {"command": "indexed", "args": ["lsp"]}}`; Neovim 0.11+:
`vim.lsp.start({ name = "indexed", cmd = { "indexed", "lsp" } })`; Zed and Helix take the
same command and args. Diagnostics are `not-in-any-collection` and `index-stale` —
severity Information, source `indexed`. There is no per-keystroke sync
(`textDocumentSync.change: 0`): the server reads the file from disk, by design.
Definition returns at most 5 locations (a whole-file range when the source has no line
span); references at most 50.

### Watching a collection

`indexed index watch <collection>` (or `-c/--collection`) first runs an incremental update
to catch up, then polls the source directory and updates once a burst of edits goes quiet,
so edits, new files and deletions show up in search without a manual `index update`. It
only works for `files` collections (remote sources have no local change signal) — any
other source type is refused with **exit 2** — and it is **opt-in**: nothing starts it
except typing the command, it runs in the foreground, and Ctrl-C is the off switch — no
daemon, no service, no config flag. `--once` runs a single update pass and exits instead
of watching.

If the watched directory disappears (unmounted drive, renamed folder), the watcher logs
an error and **keeps the last good index** instead of updating against an empty tree; it
resumes when the path returns. Three consecutive failed updates end the command with a
non-zero exit code. If the source path is already missing when the command starts,
it refuses up front with **exit 2** — updating against an unreachable source would
empty the collection. A directory that exists but cannot be read is not caught by
that check: the first update pass fails (`Permission denied`, non-zero exit) and
the last good index is kept.

Tune the cadence with `--debounce` / `--poll-interval` (seconds; both default to 2.0), or
in config:

```toml
[watch]
debounce_seconds = 2.0
poll_interval_seconds = 2.0
```

Serving the same collections to a long-lived MCP server, where a per-collection command has
nowhere to run? The server takes the same watcher behind an opt-in `[mcp]` switch — see
[Keeping an MCP server fresh](#keeping-an-mcp-server-fresh) for the keys, the startup-scope
rule and its cost.

## Roadmap

Indexed today runs parallel semantic indexes per source. The direction is one merged
knowledge graph per project — code, docs, issues, git history, connected codebases, and
accumulated lessons/memory as one structure instead of several. See
[`.spec/product.md`](.spec/product.md) § Vision and § Knowledge Graph for what's shipped
vs. planned.

## Documentation

- [Search result reference](docs/reference/search-output.md) — the `indexed.search/1` payload that `--json` and the MCP tools return, field by field
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

Retrieval quality has its own measurement: a pinned corpus and judged query set
with hit-rate@k / MRR, so a ranking change can be compared instead of argued
about. Reproduce the committed baseline and compare against it:

```bash
uv run indexed-eval run --out /tmp/report.json
uv run indexed-eval compare --report /tmp/report.json
```

See [`eval/README.md`](eval/README.md) for provenance, the metric definitions and
the measured baseline.

See [`AGENTS.md`](AGENTS.md) and [`.spec/tech.md`](.spec/tech.md) for architecture details.

## License

See [LICENSE](./LICENSE) file for details.

## Credits

The Core v1 implementation is based on [documents-vector-search](https://github.com/shnax0210/documents-vector-search) by shnax0210, licensed under MIT and modified extensively.

---

**[indexed.sh](https://indexed.sh)** · Star the repo if you find it useful!
