---
type: branch
scope: app
parent: tech.md
covers: CLI command architecture, storage-mode resolution, Rich UI, logging, MCP server (tools/resources/transports), CLI startup perf
updated: 2026-06-15
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
- **Config:** `inspect`, `update`, `set`, `validate`, `delete`
- **MCP:** `run`, `dev`, `inspect`
- **Top-level:** `init`, `migrate`, `docs`, `license` (`debug` is hidden)

---

## Storage Mode Resolution

`Global` (`~/.indexed`) vs `Local` (`./.indexed`). Resolution order:

1. CLI flag `--local` (highest; absence ≠ flag — there is no `--global`)
2. `[workspace].mode` in `config.toml`
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
same engine service functions (`core.v1.engine.services`) + `ConfigService` as the
CLI — agent sees what the user sees. Results pass through `formatting.py`
(`format_search_results_for_llm`) into a flat, LLM-optimized shape.

### Tools

Two tools (`tools.py`):

- `search(query, ctx=None)` — search across all collections.
- `search_collection(collection, query, ctx=None)` — search one named collection.

Both return a dict of ranked results; each result carries `rank`,
`relevance_score`, `collection`, `document_id`, `document_url`, `chunk_number`,
`text`. On failure they return `{"error": "..."}`.

### Resources

Listing and status are **resources**, not tools (`resources.py`):

```python
@mcp.resource("resource://collections")          # list of names
@mcp.resource("resource://collections/status")    # status for all
@mcp.resource("resource://collection/{name}")      # status for one (singular path)
```

The single-item template uses the singular `collection/{name}` on purpose: FastMCP
v3 dispatches by path shape, so a `collections/{name}` template would collide with
the static `collections` / `collections/status` routes.

### Transports

| Transport | Use Case | Implementation |
|-----------|----------|----------------|
| **stdio** (default) | Claude Desktop, Cline | stdin/stdout |
| **http** | network access | HTTP server on port 8000 |
| **sse** | Server-Sent Events | SSE streaming |
| **streamable-http** | streaming HTTP | FastMCP streamable transport |

`apps/indexed/src/indexed/mcp/cli.py` handles transport selection.

---

## CLI Startup Time

**Target:** <1s. **Actual:** ~500ms.

Techniques: lazy imports of heavy ML libs, deferred service init, minimal
module-level imports (`TYPE_CHECKING`), `__getattr__` module-level lazy loading.

```python
def __getattr__(name: str):
    # Engine service functions + heavy deps loaded on first access, not at import.
    if name == "svc_search":
        from core.v1.engine.services import search
        return search
    # …likewise svc_create / svc_update / svc_clear / svc_status,
    #   DEFAULT_INDEXER, SourceConfig
    raise AttributeError(f"module has no attribute '{name}'")
```
