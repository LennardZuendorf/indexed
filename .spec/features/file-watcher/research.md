---
type: feature-research
feature: file-watcher
parent: tech.md
updated: 2026-06-20
---

# Feature: MCP File Watcher — Research

Discovery notes from reading the codebase before design. Findings here are
distilled into [product.md](product.md) (WHAT), [tech.md](tech.md) (HOW), and
[plan.md](plan.md) (units). Kept as the trail for *why* the design looks as it
does. Cited paths are truth at exploration time.

**Architecture:** [tech.md](tech.md) · **Requirements:** [product.md](product.md)

---

## Findings

### F1 — The MCP server already has an async lifespan hook
`apps/indexed/src/indexed/mcp/server.py:49-54` builds a FastMCP server with an
`@asynccontextmanager` lifespan yielding `LifespanState` (`server.py:20-25`). This
is the natural place to start/stop a watcher task and to stash a shared re-index
manager that both the watcher and a new tool can reach (tools already read
`ctx.lifespan_context` via `mcp/config.py:resolve_config`).

### F2 — Re-index already exists and is incremental for files
`core.v1.engine.services.update([SourceConfig(...)])` → `_update_one`
(`engine/services/collection_service.py`) → `create_collection_updater`
(`engine/factories/update_collection_factory.py`). For `localFiles`,
`_build_local_files_update` uses `ChangeTracker` + persisted `state.json` to
process only added/modified files, compute deletions, and re-save state
afterwards. The CLI `index update` command rides the same service. **The feature
reuses this — no new indexing code.** An update only needs `name` + `indexer`
(path/type come from the manifest).

### F3 — Discovering folder→collection mappings
`core.v1.engine.services.status()` returns `CollectionStatus` with `source_type`
and `indexers`; filter `source_type == "localFiles"`. The watched base path is in
the manifest as `reader.basePath` (read directly, as
`update_collection_factory._populate_local_files_config` does). `status()` does
not currently expose `basePath`. Nested/overlapping base paths mean one change
can map to several collections — must be handled, not assumed 1:1.

### F4 — Stale-cache hazard (the key correctness risk)
Two caches can serve stale results inside a long-lived server:
1. `SearchService._searcher_cache` — a process-global singleton
   (`engine/services/search_service.py:300-309`), keyed `"{collection}:{indexer}"`
   (`search_service.py:65`), holding the in-memory FAISS index loaded at first
   search. A re-index rewrites the on-disk index but the cached searcher keeps the
   old one.
2. `ResponseCachingMiddleware` on the server (`server.py:58`) caches tool responses.

There is **no public API** to evict a single searcher today → drives the
`SearchService.invalidate()` addition (plan unit `file-watcher/1`).

### F5 — Watcher library: `watchfiles` is already installed
`watchfiles` (Rust-backed, asyncio-native `awatch` with built-in debounce + a
`watch_filter` hook) imports cleanly in the workspace. `watchdog` is **not**
installed. Decision: use `watchfiles` — no new dependency, drops into the FastMCP
event loop and the lifespan cancel path.

### F6 — Existing filter knobs to respect
`localFiles` collections carry `includePatterns`, `excludedDirs`,
`respectGitignore` (`connectors/files/schema.py`, with `DEFAULT_EXCLUDED_DIRS`).
The watcher should pre-filter events so churn in `.git/`, `node_modules/`, build
dirs, etc. never starts a debounce timer; `ChangeTracker` re-filters at index time
regardless, so filtering is a noise optimisation, not a correctness requirement.

### F7 — Config + CLI surfaces
`MCPConfig` (`core/v1/config_models.py:161`) is loaded in the lifespan — a natural
home for `watch_enabled` / `watch_debounce_seconds`. The CLI `mcp run`
(`mcp/cli.py:171-205`, `run_impl`) is where `--no-watch` is added; because the
server object is module-level, the flag is threaded in via a `build_server(...)`
factory (decision recorded in [plan.md](plan.md) § Key Technical Decisions).

---

## Risks (carried into tech.md)

- **Event-loop starvation** if `update()` runs inline → must offload to a thread.
- **Stale search results** if cache invalidation is missed (F4) — highest-risk item.
- **Re-index storms** from editor temp/swap writes → `watch_filter` + debounce + per-collection coalescing.
- **Concurrent `state.json` writes** for one collection → per-collection lock.
- **stdio noise** — watcher logs must go to stderr to keep the protocol channel clean.

---

## Decisions taken (from the design conversation)

1. Cache busting: add `SearchService.invalidate()` **and** clear the response cache.
2. Flag plumbing: `build_server()` factory; module-level `mcp` stays default-built.
3. Async tool: one `reindex(collection?)`; status via existing collection resource.
4. Library: `watchfiles`. Default: watch ON for all transports, opt-out via `--no-watch`.
5. Scope: `localFiles` collections under the server's active storage mode.
