---
type: branch
scope: app
parent: tech.md
covers: CLI command architecture, storage-mode resolution, Rich UI, logging, MCP server (tools/resources/transports), CLI startup perf
updated: 2026-09-02
---

# Tech Branch: App (`src/indexed/cli/`, `src/indexed/mcp/`)

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

## Engine Selection (`--engine`)

Selects v1 vs v2 for a **new** collection only (existing collections are
manifest-authoritative — the facade infers their engine, a conflicting
`--engine` fails loud). Resolution order, highest wins:

1. Leaf-command flag (e.g. `index create files --engine v2`)
2. Group-callback flag (e.g. `index create --engine v2 files`)
3. Root-callback flag (e.g. `indexed --engine v2 index create files`)
4. `INDEXED__CORE__ENGINE` env var
5. `[core] engine` in `config.toml`
6. Built-in default (`v1`)

All three CLI-flag tiers (leaf/group/root) write into the **same** `ctx.obj`
dict — Click hands a child `Context` its parent's `obj` by identity, not a
copy, so a group or leaf callback doing `ctx.obj["engine"] =
normalize_engine_selector(v)` mutates the exact object the root callback
populated. `execute_create_command`'s single `get_context_value("engine")`
read sees whichever tier actually wrote, with no extra resolution code. Each
tier writes **only when the flag was explicitly passed** (guard on
`isinstance(value, str)`), so an unset flag at any level never clobbers a
value set by an outer level with `None`. This is the general pattern for
adding a flag at an intermediate level of the Typer app tree — mirror the
root callback's write, don't invent a new resolution tier or thread a new
parameter through every intermediate function.

All four surfaces that can reject an invalid engine value
(`--engine`, env, `config set core.engine`, hand-edited `config.toml`) share
one normalizer, `composition.normalize_engine_selector` — every surface
raises the identical single-line `Invalid engine 'x'; expected one of: 1, 2,
v1, v2`, never a raw pydantic `ValidationError` dump. `config set`'s
`core.engine` special case and `resolve_engine_selector`'s config.toml
branch both call it directly rather than parsing pydantic's error shape.

---

## Rich UI Patterns

All terminal output via `rich`:

- **Info cards** — `Panel`-based cards for search results / object summaries
- **Status indicators** — colored icons (`✓`, `✗`, `!`)
- **Progress** — spinner + bar for long-running indexing

### Theme

- **Accent:** teal (`#00D4AA`) for commands/highlights
- **Secondary:** dim/grey for metadata

### Markup safety

User-supplied query text and indexed content are **Rich-escaped**
(`rich.markup.escape` / `Text`) before display — never build markup from
untrusted content. A `[/...]` or `arr[i]` in a query or document must render
literally, never raise `MarkupError` and never silently drop the text.

The same parser also runs over **static option help text** — a bracketed
`[dotted.config.key]` inside a `typer.Option(help=...)` string is parsed as a
style tag and silently dropped from rendered `--help` output (no error, no
warning). Never write a bracketed config key in a `help=` string; write it
unbracketed (`core.v1.search.max_docs`, not `[core.v1.search.max_docs]`) as
`--limit` and `--rerank` both do. A test asserting a `--help` string names a
config key must assert the key text itself appears in rendered output, not
just that the flag exists.

---

## Logging Strategy

`loguru`, three verbosity levels:

1. **Default (quiet)** — warnings + errors only; stdout reserved for command results
2. **Verbose (`--verbose`)** — INFO; progress steps
3. **Debug (`--log-level=DEBUG`)** — internal detail, timings, HTTP requests

---

## MCP Server

Embedded `FastMCP` server (`src/indexed/mcp/`), decomposed into
`server.py`, `tools.py`, `resources.py`, `formatting.py`, `config.py`. Reuses the
same `SearchService` + `ConfigService` as the CLI — agent sees what the user sees.

### Freshness & error envelopes

- **No response caching.** The server registers no response-caching middleware —
  a `search` after a re-index reflects the latest on-disk index (core's searcher
  cache already provides the latency win and invalidates on load).
- **Failures are surfaced, never swallowed.** A per-collection failure is reported
  in the result envelope (an `{error: …}` entry), never dropped as a silent
  "0 matches"; the boundary envelopes **every** exception (core raises
  `IndexedError` for missing/corrupt collections) so the agent sees "index
  failed", not empty results.

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

`src/indexed/mcp/cli.py` handles transport selection.

---

## Storage Indicator Timing

The storage-mode indicator (`display_storage_mode_for_command`) must print before any
connector prompt (URL, credentials). Each connector command hoists the indicator to its
top using a module-level helper:

```python
def _display_storage_indicator(verbose: bool, log_level: Optional[str]) -> None:
    """Print storage-mode indicator unless verbose/debug output is already active."""
    if not verbose and not (log_level and log_level.upper() in ("INFO", "DEBUG")):
        from ...utils.storage_info import display_storage_mode_for_command
        display_storage_mode_for_command(console)
```

**Why not `is_verbose_mode()`?** At command-function top, `setup_root_logger` has not
yet run (it lives inside `execute_create_command`), so `is_verbose_mode()` always
returns its module-level default (`False`) regardless of flags. The direct `verbose`
and `log_level` params are the only reliable source before logger setup.

---

## CLI Startup Time

**Target:** <1s. **Actual:** ~500ms.

Techniques: lazy imports of heavy ML libs, deferred service init, minimal
module-level imports (`TYPE_CHECKING`), `__getattr__` module-level lazy loading.

```python
def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "svc_search":
        from indexed.core.v1.engine import search
        return search
    if name == "SourceConfig":
        from indexed.core.v1.engine import SourceConfig
        return SourceConfig
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```
