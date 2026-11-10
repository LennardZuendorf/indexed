---
type: branch
scope: app
parent: tech.md
covers: CLI command architecture, storage-mode resolution, Rich UI, logging, MCP server (tools/resources/transports), LSP server (stdio JSON-RPC), CLI startup perf
updated: 2026-11-02
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

Log records never touch stdout. The CLI wires `bootstrap_logging` to a
stderr-backed Rich console (`cli/utils/console.py::log_console`), while
human-facing output and progress displays keep the stdout `console`. Under
`--simple-output` (and `--json` where the result-shape work adds it) stdout is
the payload and nothing else, so a `json.loads(stdout)` consumer never has to
strip a log line — including a WARNING raised mid-command.

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
  in `collection_errors` on the success payload, never dropped as a silent
  "0 matches"; the boundary envelopes **every** exception (core raises
  `IndexedError` for missing/corrupt collections) so the agent sees "index
  failed", not empty results.

### Tools

`tools.register_tools` registers `search(query)` and
`search_collection(collection, query)`. Both call `_run_search`, which passes raw
`core.engine.search` results to `build_search_payload(raw_results, query)`.
Both return the `indexed.search/1` payload documented below. Collection listing
and status use resources, not search tools.

### Resources

```python
@mcp.resource("resource://collections")          # list of names
@mcp.resource("resource://collections/status")    # status for all
@mcp.resource("resource://collection/{name}")     # status for one
```

### Transports

| Transport | Use Case | Implementation |
|-----------|----------|----------------|
| **stdio** | Claude Desktop, Cline | default, stdin/stdout |
| **http** | network access | HTTP server on port 8000 |
| **sse** | Server-Sent Events | SSE streaming |

`src/indexed/mcp/cli.py` handles transport selection.

## LSP Server (`indexed lsp`)

`src/indexed/lsp/` is a fourth presentation surface (peer of `cli`/`mcp`),
served by `indexed lsp` over stdio. Tier 0 scope: `workspace/symbol` and
`textDocument/hover`, nothing else. Full detail:
[features/lsp-tier0/tech.md](features/lsp-tier0/tech.md).

- **Framing is LSP's, not MCP's**: `Content-Length: N\r\n\r\n<utf-8 json>`
  (`lsp/protocol.py`); the MCP stdio transport is newline-delimited and cannot
  be reused. stdout belongs to the protocol — log records go to stderr.
- **Capabilities are the contract**: `initialize` advertises
  `textDocumentSync: 0`, `hoverProvider`, `workspaceSymbolProvider` and nothing
  else. (Tier 1 replaces `textDocumentSync: 0` with open/close/save
  notifications and adds `definitionProvider`/`referencesProvider` plus pushed
  diagnostics — see [features/lsp-tier1/tech.md](features/lsp-tier1/tech.md).)
  Anything unimplemented answers `MethodNotFound` (-32601).
- **One provenance normaliser**: `utils/provenance.py::build_locator` is the
  only locator builder — `mcp/formatting.py` (the `indexed.search/1` payload)
  and `lsp/results.py` both use it, so no surface can drift into a second
  shape. LSP ranges are 0-based; the locator's line spans are 1-based
  inclusive over 0-based chunk metadata.
- **Cost discipline**: status is cached (2 s TTL) and hover searches only the
  collection whose `manifest.reader.basePath` owns the file — no full-store
  scan per keystroke (issue #126).
- **Layer rule**: `lsp` is an "up" layer in `scripts/check_imports.py` — it may
  use only the core facade, and nothing below may import it.

---

## Search result contract (`indexed.search/1`)

**Source of truth for every machine consumer:** `indexed search --json` and the MCP
tools `search` / `search_collection`. One typed contract
(`src/indexed/protocols/results.py`), one builder
(`indexed.mcp.formatting.build_search_payload`), so the two surfaces cannot drift into
lookalikes (issues #108/#109). Downstream consumers — the eval harness (#204), the
`index-use` skill text (#222) — branch on `schema`, never on the presence of a key. The
LSP server (#241) reads the engine's results directly and reuses only this contract's
locator vocabulary (`indexed.utils.provenance`), so it cannot drift into a third
provenance shape.

```json
{
  "schema": "indexed.search/1",
  "query": "how is relevance unified",
  "counts": {"documents": 2, "hits": 3},
  "collections": ["indexed-src", "notes-v2"],
  "collection_errors": [{"collection": "jira", "error": "…"}],
  "documents": [
    {
      "collection": "indexed-src",
      "source_type": "localFiles",
      "id": "src/indexed/utils/relevance.py",
      "path": "/repo/src/indexed/utils/relevance.py",
      "url": "https://…",
      "score_kind": "l2_squared",
      "hits": [
        {
          "relevance": 0.625,
          "score": 0.75,
          "locator": {"kind": "line_span", "start_line": 18, "end_line": 19},
          "text": "HIGHER_IS_BETTER = frozenset({\"cosine\", \"rerank\"})"
        }
      ]
    }
  ]
}
```

Rules the shape encodes — each one exists because the old flat payload got it wrong:

- **Document-level facts are stated once.** `collection`, `source_type`, `id`, `path`,
  `url` and `score_kind` belong to the document; only `relevance`, `score`, `locator`
  and `text` repeat per hit. Repeating `collection`/`document_id`/`document_url` on
  every chunk was most of the old payload's token cost.
- **A locator is honest.** `kind` is `line_span` (1-based inclusive lines — what
  `grep -n` prints — plus the file when the document states no `path`), `page`
  (positive page metadata, when supplied), `headings` (prose:
  Markdown/Jira/Confluence/Outline) or `document` (position genuinely unknown).
  A range is never invented to fill the field.
  `headings` is never empty: the converters emit `headings: [""]` for whole-file
  chunks, so headings are trimmed and blank ones dropped before the kind is chosen —
  a chunk left with no headings gets `document`, not `{"kind": "headings",
  "headings": []}`.
- **`relevance` is comparable, `score` is not.** `relevance` is 0–1, higher-is-better,
  unified across engines (`indexed.utils.relevance.unified_relevance`); `score` is the
  raw engine number, only comparable within one `score_kind` (`l2_squared` = v1,
  `cosine`/`rerank` = v2).
- **Ranking is document-first.** A document's position reflects its best hit; ties keep
  discovery order (stable sort). Ranking uses full precision before four-decimal
  output rounding.
- **`source_type` is a collection fact**, taken from `manifest.reader.type`; omitted
  rather than guessed when the manifest does not say.
- **No boilerplate to strip on normal returns.** `--json` stdout is only JSON
  (logs and notices — a skipped unsearchable collection, a no-op `--rerank` — go to
  stderr); the `# <path>\n` context prefix the indexer embeds in code chunks
  is removed because `locator.path` already carries the path.
- **Failures never read as emptiness.** `collection_errors` is always present; a failed
  collection appears there, not as a silent zero. Boundary exceptions return the
  failure envelope below.
- **Machine payloads always request matched chunk content.** CLI JSON and both MCP
  tools pass `include_matched_chunks=True`, even when the search config sets it to
  false. Text and provenance are required by the fixed payload contract.
- **`--json` ignores `--compact` / `--no-content`** (they shape the human view only;
  `--simple-output`/`--json` wins). The machine payload is fixed, never flag-shaped.

### The two bodies: success and failure

A payload either carries `schema: "indexed.search/1"` or it does not, and that is the
first thing a consumer reads:

- **`schema` present** → the success shape documented above. Empty `documents`
  means no matched content was returned. `collections` lists successfully searched
  collections. Empty `collections` means **no collection was searched successfully**;
  inspect `collection_errors` to distinguish an empty store from all searches failing.
  Non-empty `collections` with empty `documents` means those collections matched nothing.
- **`schema` absent** → an error envelope, `error` holding the message. A request that
  failed never reads as "nothing matched".

| Surface | Body | Exit |
|---|---|---|
| CLI `search --json -c <name>` — collection unknown or omitted by status after an unreadable manifest | `{"error": "Collection 'x' not found"}` | `1` |
| CLI `search --json -c <name>` — known status with no indexers | `{"error": "No searchable collections available"}` | `1` |
| CLI `search --json` (all) — no collections exist | `{"error": "No collections found"}` | `0` |
| CLI `search --json` (all) — collections exist, none searchable | `{"error": "No searchable collections available"}` | `0` |
| MCP `search` — empty store / nothing searchable | *success* payload, `collections: []`, `documents: []`, `counts` zeroed | n/a (tool result) |
| CLI `search --json` / MCP `search` — one collection fails, others answer | success payload with that collection in `collection_errors` | CLI `0`; MCP n/a |
| MCP `search` / `search_collection` — caught `IndexedError` | `{"error": "…", "type": "<concrete class name>"}` (for example, `StorageError`) | n/a |
| MCP `search` / `search_collection` — unexpected search/status exception | `{"error": "Internal error: …", "type": "MCPError"}` | n/a |
| MCP `search_collection` — collection unknown on disk | `{"error": "Collection 'x' not found or has no indexers"}` — **no `type`** | n/a |

Two asymmetries are deliberate and must not surprise a harness:

- **MCP has no exit code, and one of its bodies has no `type`.** `search_collection`
  answers an unknown name with the bare `{"error"}` its clients already match on
  (`mcp/collection_errors.py`). On an error body, absence of `type` identifies
  this unknown-name case. Caught `IndexedError` instances preserve their concrete
  class as `type`; unexpected search/status failures use `MCPError`.
  Branch on `schema` first; `type` is a refinement.
- **The empty store is a CLI envelope but an MCP success payload.** The CLI says
  `{"error": "No collections found"}`, the MCP tool returns the success shape with
  `collections: []`. Empty `collections` means no collection was searched
  successfully; inspect `collection_errors` to distinguish an empty store from all
  searches failing. Empty `documents` with non-empty `collections` means those
  collections matched nothing.

**Errors that escape the command** (`ConfigurationError`, `StorageError`, … raised
before a payload exists) go to the CLI's top-level handler. It prints a Rich error
panel to **stdout** and exits with the mapped code (`1`, `2` for config, `3` for
storage). This exceptional stdout is not JSON. Check the exit code before parsing
stdout; a non-zero exit is a failed request. An `error` body reports a failure or
an empty store, while empty `collections` means no collection was searched
successfully. Inspect `collection_errors` for partial or all-collection failures.
The search bodies above are pinned:
`tests/unit/indexed/mcp/test_search_payload_golden.py` (CLI and MCP envelopes),
`tests/unit/indexed/mcp/test_tools_collection_errors.py` (unknown vs unusable
collection) and `tests/unit/indexed/knowledge/commands/test_search.py` (the CLI
`{"error": "No searchable collections available"}` rows, exit codes included).

Versioning: bump `SEARCH_SCHEMA` on any incompatible change.

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
