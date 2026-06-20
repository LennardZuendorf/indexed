---
type: feature-exploration
scope: mcp-file-watcher
parent: ../../tech-app.md
status: exploration (pre-design, not yet approved)
updated: 2026-06-20
---

# Feature Exploration: MCP File Watcher + Async Re-index Tool

Exploration only — captures findings, integration points, design options, and
open questions. **No code written yet.** Follows ASK → PLAN → CONFIRM → EXECUTE;
this doc is the PLAN input that needs CONFIRM before EXECUTE.

## 1. Goal (restated)

Two related capabilities for the MCP server (`apps/indexed/src/indexed/mcp/`):

1. **Auto file watcher** — active by default during MCP server runtime (opt-out
   via flag). Watches the folders that back `localFiles` collections and, after a
   sensible **debounce window**, automatically triggers an **incremental
   re-index** when files in those folders are added / modified / removed.
2. **Async re-index MCP tool** — a new tool an agent can call to trigger a
   re-index in the background (non-blocking), returning immediately.

Both share the same underlying machinery: discover file collections → run the
existing incremental update → invalidate stale search caches, all off the event
loop.

## 2. Key findings (how the current system works)

### 2.1 MCP server has an async lifespan — the natural hook point
`server.py` builds a FastMCP server with an `@asynccontextmanager` lifespan that
yields a `LifespanState` TypedDict (`mcp_config`, `search_config`). This is the
ideal place to **start the watcher task on enter and cancel it on exit**, and to
stash a shared re-index manager into lifespan state so both the watcher and the
new tool reach the same job queue.

- `server.py:49-54` — `lifespan()` (currently does nothing but load config).
- `server.py:20-25` — `LifespanState` (would gain `reindex_manager` / `watcher`).
- Tools receive `ctx`; `config.py:resolve_config` already reads
  `ctx.lifespan_context[...]`, so a tool can fetch the manager the same way.

### 2.2 Re-index already exists and is incremental
The `update` flow is exactly the re-index we need and is already change-aware for
files:

- `core.v1.engine.services.update([SourceConfig(...)])` → `_update_one` →
  `create_collection_updater` (`update_collection_factory.py`).
- For `localFiles`, `_build_local_files_update` uses the **`ChangeTracker`** +
  persisted `state.json` to process only added/modified files and to compute
  deletions, then **saves fresh state** after the run (`_UpdatingCollectionCreator`).
- The CLI `index update` command calls the same service
  (`knowledge/commands/update.py`), so we are reusing a proven path. The
  `SourceConfig` for an update only needs `name` + `indexer` (type/path unused on
  update — they come from the manifest); indexer comes from
  `status([name])[0].indexers[0]`.

**Implication:** the watcher/tool do *not* re-implement indexing — they call
`update(...)`. A burst of file changes collapses into one incremental update.

### 2.3 Discovering which collections back a folder
- `core.v1.engine.services.status()` returns `CollectionStatus` with
  `source_type` and `indexers`. Filter `source_type == "localFiles"`.
- The watched **base path** is in the manifest: `reader.basePath`
  (`update_collection_factory._populate_local_files_config`,
  `inspect_service` reads `reader.type`). `status()` does *not* currently expose
  `basePath` — we read it from `manifest.json` directly (as several call sites
  already do) or extend the status DTO.
- A changed file maps to a collection when it lives under that collection's
  `basePath`. **Nested/overlapping base paths mean one change can fan out to
  several collections** — must handle, not assume 1:1.

### 2.4 Stale-cache hazard (the critical correctness concern)
After a re-index, two caches can serve **stale** results inside the long-lived
server:

1. `SearchService._searcher_cache` — a process-global singleton
   (`search_service.py:300-309`) keyed `"{collection}:{indexer}"`. It holds the
   **in-memory FAISS index loaded at first search**; a re-index rewrites the
   on-disk index but the cached searcher keeps the old one.
2. `ResponseCachingMiddleware` on the server (`server.py:58`) caches tool
   responses (e.g. `search`).

**Any re-index must invalidate the searcher cache entry for affected collections**
(and ideally the response cache). There is currently **no public API** to evict a
single searcher — this is a small required addition to `SearchService`
(e.g. `invalidate(collection_name)`).

### 2.5 Watcher library — `watchfiles` is already available
- `watchfiles` **is installed** (Rust-backed, asyncio-native `awatch`, built-in
  debounce via `debounce`/`step` ms params, and a `watch_filter` hook).
- `watchdog` is **not** installed.
- **Recommendation: use `watchfiles`.** Its `awatch(*paths, stop_event=...)`
  async generator drops cleanly into the FastMCP event loop and the lifespan
  cancel path, and it already debounces bursts. Avoids adding a new dependency.

### 2.6 Existing filtering knobs to respect
`localFiles` collections carry `includePatterns`, `excludedDirs`,
`respectGitignore` (schema `FileSystemConfig`, defaults incl. `DEFAULT_EXCLUDED_DIRS`).
The watcher should pre-filter events (via `watch_filter`) so churn in `.git/`,
`node_modules/`, build dirs, etc. never starts a debounce timer. `ChangeTracker`
re-filters at index time anyway, so filtering is an optimization for noise, not a
correctness requirement.

### 2.7 Config surfaces
- `MCPConfig` (`config_models.py:161`) already exists and is loaded in the
  lifespan — a natural home for watcher settings (`watch_enabled`,
  `watch_debounce_seconds`, …). There is even a latent `enable_async_pool` flag.
- CLI `mcp run` (`mcp/cli.py:171-205`, `run_impl`) is where a `--watch/--no-watch`
  flag is added and threaded into `mcp.run(...)`. Note the server object is module
  -level in `server.py`; the flag needs to reach the lifespan (env var, module
  state, or building the server lazily — see open questions).

## 3. Proposed design (for discussion)

### 3.1 Components
- **`ReindexManager`** (new, in `mcp/`): owns an `asyncio` job model.
  - Per-collection **lock / coalescing**: never run two updates for the same
    collection concurrently; if changes arrive mid-run, mark "dirty" and re-run
    once after.
  - Runs the blocking `update(...)` via `asyncio.to_thread` (or a single-worker
    executor) so the event loop stays responsive.
  - On success: call `SearchService.invalidate(collection)` (+ response-cache
    clear) so the next search sees fresh data.
  - Tracks per-job status (`queued`/`running`/`done`/`error`, timestamps,
    counts) for the async tool to report.
  - Lives in `LifespanState` so the watcher and the MCP tool share one instance.

- **`CollectionWatcher`** (new, in `mcp/`): an async task started by the lifespan.
  - Builds the path→collections map from `status()` + manifests at startup.
  - `async for changes in awatch(*base_paths, watch_filter=..., stop_event=...)`:
    map each changed path to affected collection(s), then ask `ReindexManager` to
    schedule a **debounced** re-index per collection.
  - Debounce: rely on `watchfiles` burst-debounce **plus** a short per-collection
    settle window in the manager (configurable, default ~2–5 s) so rapid saves
    batch into one update.

- **Lifespan wiring** (`server.py`): build manager + watcher on enter, cancel +
  await on exit. Respect the `--no-watch` flag / `watch_enabled` config.

- **New MCP tool `reindex`** (`mcp/tools.py`):
  - `reindex(collection: Optional[str] = None, ctx=...)` → schedules background
    re-index of one or all file collections via the shared `ReindexManager`,
    returns immediately with a job id + accepted collections.
  - Optionally a `reindex_status` tool (or extend the existing
    `resource://collection/{name}`) to report job state.

### 3.2 Config additions (draft)
```toml
[mcp]
watch_enabled = true          # opt-out via --no-watch
watch_debounce_seconds = 3.0  # settle window before re-indexing a collection
# watch_paths could be auto (all localFiles collections) — default auto
```

### 3.3 CLI
```
indexed mcp run [--watch / --no-watch]   # default: watch on
```

## 4. Open questions (need CONFIRM before EXECUTE)
1. **Watch scope across transports?** Watcher only makes sense for a long-lived
   server. Enable for all transports (stdio/http/sse) or warn for stdio (short
   sessions)? Default proposal: all transports, on by default.
2. **Cache invalidation reach.** Is adding `SearchService.invalidate()` + clearing
   the response-cache acceptable, or do you want re-index to also bust the
   FastMCP `ResponseCachingMiddleware` more aggressively?
3. **Debounce default** (proposing 3 s settle window) and whether it should be
   user-configurable via `[mcp]` config (proposed yes).
4. **Async tool surface.** One `reindex(collection?)` tool returning a job id,
   plus status via the existing collection resource — or a dedicated
   `reindex_status` tool too?
5. **Flag→lifespan plumbing.** Preferred mechanism to pass `--no-watch` into the
   module-level server lifespan: env var, module-level setter, or refactor
   `server.py` to a `build_server(...)` factory? (Factory is cleanest but touches
   `fastmcp.json` / `fastmcp_server.py` re-export.)
6. **Storage mode.** Watch only the active storage mode's collections (global vs
   local), matching how the server already resolves collections? Default: yes,
   follow existing resolution.

## 5. Rough implementation sketch (post-approval)
1. `SearchService.invalidate(name)` + small unit test.
2. `ReindexManager` (coalescing + to_thread + status) + tests.
3. `CollectionWatcher` over `watchfiles.awatch` with `watch_filter` + path map.
4. Lifespan wiring in `server.py`; `MCPConfig` fields; `--watch/--no-watch` in
   `mcp/cli.py`.
5. `reindex` (+ optional `reindex_status`) tool in `mcp/tools.py`.
6. Tests (mock `awatch`, assert debounce coalescing, cache invalidation) and docs
   (`tech-app.md`, README MCP section). Keep >85% coverage; ruff + mypy strict.

## 6. Risks
- **Event-loop starvation** if `update()` runs inline — must offload to a thread.
- **Stale search results** if cache invalidation is missed (§2.4) — highest-risk
  correctness item.
- **Re-index storms** from editors writing temp/swap files — mitigated by
  `watch_filter` + debounce + per-collection coalescing.
- **Concurrent state.json writes** if the same collection re-indexes twice at once
  — prevented by the per-collection lock.
- **stdio noise** — watcher logs must not corrupt the stdio MCP channel (log to
  stderr / respect `log_level`).
