---
type: feature-design
scope: mcp-file-watcher
parent: ../../tech-app.md
status: design (pending CONFIRM before EXECUTE)
updated: 2026-06-20
---

# Feature Design: MCP File Watcher + Async Re-index Tool

Detailed design. Builds on [exploration.md](exploration.md). **No code yet** —
this is the artifact to approve before implementation. Decisions locked in §0.

## 0. Locked decisions (from CONFIRM)
1. **Cache busting:** add `SearchService.invalidate(name)` AND clear the FastMCP
   response cache after each successful re-index.
2. **Flag plumbing:** refactor `server.py` to a `build_server(...)` factory that
   accepts watch settings; module-level `mcp` becomes a default-built instance so
   `fastmcp.json` / `fastmcp_server.py` keep working.
3. **Async tool:** single `reindex(collection?)` tool returning a job id; status
   is read via the existing `resource://collection/{name}` (extended) — no
   separate status tool.
4. **Library:** `watchfiles` (already installed).
5. **Default:** watcher ON for all transports; opt-out via `--no-watch`.
6. **Scope:** watch `localFiles` collections resolved under the server's active
   storage mode.

## 1. Architecture overview

```
                       FastMCP lifespan (server.py)
                                  │ on enter
        ┌─────────────────────────┼──────────────────────────┐
        ▼                         ▼                           ▼
  ReindexManager            CollectionWatcher           LifespanState
  (job queue, locks,   ─▶   (watchfiles.awatch     ─▶   { mcp_config,
   to_thread runner,        over base paths,             search_config,
   cache invalidation)      path→collection map,         reindex_manager,
        ▲                    debounce/filter)             watcher_task }
        │ schedule(name)          │ on file event
        │                         ▼
   reindex() MCP tool      maps path → collections → manager.schedule(name)
        │
        └─▶ returns job id immediately
```

- **One** `ReindexManager` instance per server, shared (via `LifespanState`) by
  the watcher and the `reindex` tool — single source of truth for job state and
  the per-collection lock.
- The watcher and the tool are **producers**; the manager is the **consumer** that
  serializes work per collection and offloads the blocking `update()` to a thread.

## 2. Component specs

### 2.1 `SearchService.invalidate()` (core change)
File: `packages/indexed-core/src/core/v1/engine/services/search_service.py`

Add to the class and a functional wrapper:

```python
class SearchService:
    def invalidate(self, collection_name: str | None = None) -> int:
        """Evict cached searcher(s). None → clear all. Returns # evicted."""
        if collection_name is None:
            n = len(self._searcher_cache)
            self._searcher_cache.clear()
            return n
        prefix = f"{collection_name}:"
        keys = [k for k in self._searcher_cache if k.startswith(prefix)]
        for k in keys:
            del self._searcher_cache[k]
        return len(keys)

# module-level functional wrapper (mirrors search()):
def invalidate(collection_name: str | None = None,
               collections_path: str | None = None) -> int:
    return _get_service(collections_path).invalidate(collection_name)
```

- Cache keys are `"{collection}:{indexer}"`, so prefix-match covers all indexers
  of a collection (search_service.py:65).
- Export `invalidate` from `core.v1.engine.services.__init__`.
- **Why core, not mcp:** the singleton `_default_service` is what MCP search uses
  (`tools.py` → `svc_search`), so invalidation must hit that same instance.

### 2.2 Response-cache clear
The server adds `ResponseCachingMiddleware()` (server.py:58). After a successful
re-index the manager must drop cached `search`/`search_collection` responses.

- Investigate FastMCP's middleware API for a public clear/evict; the middleware
  instance will be **held on the manager** at construction.
- Fallback if no public API: reconstruct/replace the middleware's cache store, or
  (last resort) skip response-cache and rely only on searcher invalidation +
  a short middleware TTL. **Spike task in §6 step 0.**

### 2.3 `ReindexManager` (new)
File: `apps/indexed/src/indexed/mcp/reindex.py`

Responsibilities: schedule, coalesce, serialize-per-collection, run off-loop,
invalidate caches, track status.

```python
JobState = Literal["queued", "running", "done", "error"]

@dataclass
class ReindexJob:
    job_id: str
    collection: str
    state: JobState
    queued_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    documents_delta: int | None = None
    chunks_delta: int | None = None

class ReindexManager:
    def __init__(self, *, debounce_seconds: float,
                 search_invalidate: Callable[[str], int],
                 response_cache_clear: Callable[[], None],
                 collections_path: str | None = None) -> None: ...

    def schedule(self, collection: str) -> ReindexJob:
        """Idempotent: coalesces into an in-flight/queued job for the same
        collection. Starts (or restarts) the per-collection debounce timer.
        Returns the active job (existing or new). Non-blocking."""

    async def aclose(self) -> None:
        """Cancel timers + in-flight tasks; await graceful stop."""

    def status(self, collection: str | None = None) -> list[ReindexJob]: ...
    def latest(self, collection: str) -> ReindexJob | None: ...
```

Internals:
- `self._locks: dict[str, asyncio.Lock]` — one per collection (serialize updates;
  prevents concurrent `state.json` writes).
- `self._jobs: dict[str, ReindexJob]` — latest job per collection (+ small history
  optional).
- `self._dirty: set[str]` + `self._timers: dict[str, asyncio.TimerHandle|Task]` —
  debounce: each `schedule()` (re)arms a `debounce_seconds` timer; on fire, run
  once. If new changes land while running, mark dirty → re-run once after.
- Runner:
  ```python
  async def _run(self, collection: str):
      async with self._locks[collection]:
          job.state = "running"; job.started_at = now()
          before = status([collection])[0]            # counts before
          src = SourceConfig(name=collection, type="localFiles",
                             base_url_or_path="", indexer=before.indexers[0])
          await asyncio.to_thread(svc_update, [src])  # BLOCKING → thread
          self._search_invalidate(collection)
          self._response_cache_clear()
          after = status([collection])[0]
          job.documents_delta = after.number_of_documents - before.number_of_documents
          ...
          job.state = "done"; job.finished_at = now()
  ```
- Errors: catch, set `state="error"`, `error=str(e)`, log to **stderr** (never
  stdout — stdio transport). Watcher keeps running.
- Uses `core.v1.engine.services.update` (aliased `svc_update`) and `status`.

### 2.4 `CollectionWatcher` (new)
File: `apps/indexed/src/indexed/mcp/watcher.py`

```python
class CollectionWatcher:
    def __init__(self, manager: ReindexManager, *,
                 collections_path: str | None = None) -> None: ...

    def build_path_map(self) -> dict[Path, list[str]]:
        """{ resolved basePath: [collection names] } for all localFiles
        collections (from status() + manifest reader.basePath). Supports
        nested/overlapping paths (a file may map to several collections)."""

    async def run(self, stop_event: anyio.Event) -> None:
        """async for changes in awatch(*paths, watch_filter=self._keep,
                                       stop_event=stop_event):
               for _change_type, path in changes:
                   for coll in self._affected(path):
                       self._manager.schedule(coll)"""

    def _keep(self, change, path: str) -> bool:
        """watch_filter: drop events under excluded dirs / gitignored /
        non-matching include patterns to avoid debounce churn."""
```

- `awatch` paths = the **distinct base paths** (watch each tree once even if it
  backs multiple collections); `_affected(path)` resolves which collections a
  changed file belongs to by `path.is_relative_to(base)`.
- Filtering reuses `connectors.files.schema.DEFAULT_EXCLUDED_DIRS` and each
  collection's `includePatterns` / `respectGitignore` (best-effort; `ChangeTracker`
  is still the source of truth at index time).
- `build_path_map()` is computed at startup; **rebuild on demand** is a follow-up
  (collections created mid-session won't be watched until restart — documented
  limitation, acceptable for v1).

### 2.5 Server factory + lifespan wiring
File: `apps/indexed/src/indexed/mcp/server.py`

```python
@dataclass(frozen=True)
class WatchSettings:
    enabled: bool = True
    debounce_seconds: float = 3.0

def build_server(watch: WatchSettings | None = None) -> FastMCP:
    response_cache = ResponseCachingMiddleware()
    mcp = FastMCP("Indexed MCP Server",
                  lifespan=_make_lifespan(watch, response_cache))
    mcp.add_middleware(response_cache)
    register_tools(mcp, _get_search_config)        # + reindex tool
    register_resources(mcp, _get_mcp_config)
    return mcp

# Backwards-compatible module-level instance for fastmcp.json / re-export:
mcp = build_server()
```

`_make_lifespan` builds the manager + watcher, merges `WatchSettings` with
`MCPConfig` (flag/explicit setting wins over config), starts the watcher task on
enter, and on exit cancels the task + `await manager.aclose()`:

```python
async with anyio.create_task_group() as tg:
    if effective.enabled:
        manager = ReindexManager(debounce_seconds=effective.debounce_seconds,
                                  search_invalidate=svc_invalidate,
                                  response_cache_clear=response_cache_clear_fn)
        watcher = CollectionWatcher(manager)
        tg.start_soon(watcher.run, stop_event)
    yield {"mcp_config": ..., "search_config": ...,
           "reindex_manager": manager}   # None if disabled
    stop_event.set()                      # triggers awatch stop + aclose
```

- `LifespanState` gains `reindex_manager: ReindexManager | None`.
- The flag→lifespan path is now clean: `run_impl` calls
  `build_server(WatchSettings(enabled=not no_watch, ...))` instead of importing the
  module-level `mcp` — **for the `indexed mcp run` path**. The module-level `mcp`
  (used by `fastmcp run`) keeps watch-on defaults.

### 2.6 `reindex` MCP tool
File: `apps/indexed/src/indexed/mcp/tools.py`

```python
@mcp.tool
def reindex(collection: Optional[str] = None,
            ctx: Optional[Context] = None) -> Dict[str, Any]:
    """Trigger a background, incremental re-index of file-based collection(s).
    Returns immediately with job id(s). Poll status via the
    `resource://collection/{name}` resource (reindex section)."""
    manager = _get_manager(ctx)   # from lifespan_context["reindex_manager"]
    if manager is None:
        return {"error": "Re-indexing is disabled (server started with --no-watch)"}
    targets = [collection] if collection else _all_file_collections()
    jobs = [manager.schedule(c) for c in targets]
    return {"accepted": [{"collection": j.collection, "job_id": j.job_id,
                          "state": j.state} for j in jobs]}
```

- `_get_manager(ctx)` mirrors `resolve_config` (reads `ctx.lifespan_context`).
- If `--no-watch` disabled the manager, the tool can either return the disabled
  error (above) **or** we always construct the manager (even when the *watcher* is
  off) so manual `reindex` still works. **Recommended:** always build the manager;
  `--no-watch` only disables the *automatic watcher*, not the manual tool. (Update
  §2.5 to always build manager, gate only `watcher.run` on `enabled`.)

### 2.7 Resource extension (status via existing resource)
File: `apps/indexed/src/indexed/mcp/resources.py`

Extend `_format_status` / `collection_status` to include a `reindex` block when a
manager is present:

```json
"reindex": {"state": "running", "job_id": "...", "started_at": "...",
            "documents_delta": null, "error": null}
```

Pull from `manager.latest(name)` via `ctx.lifespan_context`.

### 2.8 Config additions
File: `packages/indexed-core/src/core/v1/config_models.py` (`MCPConfig`)

```python
watch_enabled: bool = Field(default=True, description="Auto file watcher for localFiles collections")
watch_debounce_seconds: float = Field(default=3.0, ge=0.0, le=60.0,
    description="Settle window before re-indexing after file changes")
```

Precedence: CLI `--no-watch` > `[mcp].watch_enabled` > default(true).

### 2.9 CLI flag
File: `apps/indexed/src/indexed/mcp/cli.py` (`run` + `run_impl`)

```python
no_watch: bool = typer.Option(False, "--no-watch",
    help="Disable the automatic file watcher / auto re-index")
```
`run_impl` builds the server via `build_server(WatchSettings(enabled=not no_watch))`
and runs it (instead of importing module-level `mcp`).

## 3. Sequence flows

**Auto path:** file saved → `awatch` emits (post-filter) → watcher maps to
collection(s) → `manager.schedule()` arms 3 s debounce → timer fires → per-collection
lock → `update()` in thread → `SearchService.invalidate()` + response-cache clear →
job `done`. Burst of saves within 3 s ⇒ one update.

**Manual path:** agent calls `reindex("docs")` → `manager.schedule("docs")` →
returns `{job_id, state:"queued"}` immediately → same runner → agent reads
`resource://collection/docs` to see `reindex.state == "done"`.

**Shutdown:** lifespan exit → `stop_event.set()` → `awatch` stops, `manager.aclose()`
cancels timers + awaits in-flight update.

## 4. File-by-file change list
| File | Change |
|------|--------|
| `core/.../services/search_service.py` | add `invalidate()` + functional wrapper |
| `core/.../services/__init__.py` | export `invalidate` |
| `core/v1/config_models.py` | `MCPConfig.watch_enabled`, `watch_debounce_seconds` |
| `apps/.../mcp/reindex.py` | **new** `ReindexManager`, `ReindexJob` |
| `apps/.../mcp/watcher.py` | **new** `CollectionWatcher` |
| `apps/.../mcp/server.py` | `build_server()` factory, lifespan wiring, state field |
| `apps/.../mcp/tools.py` | new `reindex` tool + `_get_manager` |
| `apps/.../mcp/resources.py` | add `reindex` block to status |
| `apps/.../mcp/cli.py` | `--no-watch` flag → `build_server(...)` |
| `tests/unit/...` | manager (coalesce/lock/invalidate), watcher (mock awatch), tool, cli flag |
| `.spec/tech-app.md`, `README` | document watcher + tool |

## 5. Test plan (>85% coverage, mypy strict, ruff)
- **`SearchService.invalidate`**: seeds cache, asserts prefix eviction + count.
- **`ReindexManager`**: (a) two `schedule()` within debounce → one `update` call
  (mock `svc_update`); (b) per-collection lock serializes; (c) success →
  `invalidate` + cache-clear called; (d) `update` raises → job `error`, watcher
  unaffected; (e) `aclose()` cancels cleanly.
- **`CollectionWatcher`**: monkeypatch `awatch` to yield synthetic change sets →
  assert correct `schedule()` calls; `build_path_map` with nested base paths;
  `_keep` filter drops excluded dirs.
- **`reindex` tool**: returns job ids; `--no-watch`/no-manager behavior; all vs
  single collection.
- **CLI**: `mcp run --no-watch` builds server with watcher disabled (assert via
  injected `build_server` spy).
- Use `asyncio`/`anyio` test helpers; no real filesystem waits (drive timers).

## 6. Implementation order (post-approval)
0. **Spike:** confirm FastMCP `ResponseCachingMiddleware` exposes a clear/evict
   hook; if not, settle the fallback (§2.2). *(De-risks the cache decision.)*
1. `SearchService.invalidate()` + export + test.
2. `ReindexManager` + tests (pure asyncio, mocked `update`).
3. `CollectionWatcher` + tests (mocked `awatch`).
4. `server.build_server()` factory + lifespan wiring + `MCPConfig` fields.
5. `reindex` tool + resource status block.
6. `cli.py --no-watch` plumbing.
7. Docs + full suite + ruff/mypy.

## 7. Limitations (v1, documented)
- Collections created mid-session aren't watched until restart (path map built at
  startup). Follow-up: periodic/triggered rebuild.
- Watcher targets the server's active storage mode only.
- `reindex` history is "latest per collection" (no long job log).
