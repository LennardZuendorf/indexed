---
type: branch
scope: app
parent: tech.md
covers: CLI command architecture, storage-mode resolution, Rich UI, logging, MCP server (tools/resources/transports), CLI startup perf
updated: 2026-06-09
---

# Tech Branch: App (`apps/indexed`)

The user-facing application — Typer CLI + embedded FastMCP server. UI layer only;
business logic lives in services/core (see [tech.md](tech.md) § Architectural Rules).

**Parent: [tech.md](tech.md).** Config resolution detail: [tech-config.md](tech-config.md).

---

## Command Architecture

### Entry point (`app.py`)

A Typer callback handles global setup (logging, storage-mode resolution) before any
command runs. Resolved `mode_override` is stored on `ctx.obj` for subcommands.

```python
@app.callback(invoke_without_command=True)
def _init_app(ctx: typer.Context, local: bool = typer.Option(False, "--local"), ...):
    setup_root_logger(...)
    ctx.ensure_object(dict)
    ctx.obj["mode_override"] = "local" if local else None
```

### Command groups

Organized in subdirectories, exposed flat for usability:

- **Knowledge:** `create`, `search`, `inspect`, `update`, `remove` (as `index create`, …)
- **Config:** `inspect`, `set`, `validate`
- **MCP:** `run`, `dev`, `inspect`

---

## Storage Mode Resolution

`Global` (`~/.indexed`) vs `Local` (`./.indexed`). Resolution order:

1. CLI flag `--local` / `--global` (highest)
2. `storage.mode` in `config.toml`
3. Presence of `./.indexed/` → Local
4. Global (fallback)

Full single-source config detail: [tech-config.md](tech-config.md).

---

## Rich UI Patterns

All terminal output via `rich`:

- **Info cards** — `Panel`-based cards for search results / object summaries
- **Status indicators** — colored icons (`✓`, `✗`, `!`)
- **Progress** — spinner + bar for long-running indexing

### Theme

- **Accent:** teal (`#00D4AA`) for commands/highlights
- **Secondary:** dim/grey for metadata

---

## Logging Strategy

`loguru`, three verbosity levels:

1. **Default (quiet)** — warnings + errors only; stdout reserved for command results
2. **Verbose (`--verbose`)** — INFO; progress steps
3. **Debug (`--log-level=DEBUG`)** — internal detail, timings, HTTP requests

---

## MCP Server

Embedded `FastMCP` server (`apps/indexed/src/indexed/mcp/`), decomposed into
`server.py`, `tools.py`, `resources.py`, `formatting.py`, `config.py`. Reuses the
same `SearchService` + `ConfigService` as the CLI — agent sees what the user sees.

### Tools

```python
from fastmcp import FastMCP
mcp = FastMCP("indexed")

@mcp.tool()
def search(query: str, collection: str | None = None) -> dict:
    """Search indexed collections."""
    results = index.search(query, collection)
    return {"query": query, "results": [
        {"text": c.text, "score": c.score, "source": c.source, "collection": c.collection}
        for c in results]}

@mcp.tool()
def list_collections() -> dict:
    return {"collections": [c.name for c in index.list_collections()]}

@mcp.tool()
def collection_status(name: str) -> dict:
    s = index.get_status(name)
    return {"name": s.name, "document_count": s.document_count,
            "chunk_count": s.chunk_count, "embedding_model": s.embedding_model}
```

### Resources

```python
@mcp.resource("resource://collections")          # list of names
@mcp.resource("resource://collections/status")    # status for all
@mcp.resource("resource://collections/{name}")     # status for one
```

### Transports

| Transport | Use Case | Implementation |
|-----------|----------|----------------|
| **stdio** | Claude Desktop, Cline | default, stdin/stdout |
| **http** | network access | HTTP server on port 8000 |
| **sse** | Server-Sent Events | SSE streaming |

`apps/indexed/src/indexed/mcp/cli.py` handles transport selection.

---

## CLI Startup Time

**Target:** <1s. **Actual:** ~500ms.

Techniques: lazy imports of heavy ML libs, deferred service init, minimal
module-level imports (`TYPE_CHECKING`), `__getattr__` module-level lazy loading.

```python
def __getattr__(name: str):
    if name == "index":
        from core.v1 import Index
        return Index()
    raise AttributeError(f"module has no attribute '{name}'")
```
