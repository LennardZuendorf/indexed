---
type: feature-tech
feature: file-watcher
sibling: product.md
parent: ../../tech.md
updated: 2026-06-21
---

# Feature: MCP File Watcher — Architecture

The watcher and the `reindex` tool are thin producers over the existing
`core.v1.engine.services.update` pipeline. A single `ReindexManager` (held in the
FastMCP lifespan state) serializes work per collection, runs the blocking
`update()` off the event loop, and invalidates search caches on success. A
`CollectionWatcher` task drives it from `watchfiles.awatch`; the `reindex` tool
drives the same manager on demand.

**Parent:** [../../tech.md](../../tech.md) (see [tech-app.md](../../tech-app.md) § MCP server, [tech-core.md](../../tech-core.md) § services)
**Requirements:** [product.md](product.md)
**Design:** [design.md](design.md)
**Plan:** [plan.md](plan.md)
**Discovery:** [research.md](research.md)

---

## Files

```
packages/indexed-core/src/core/v1/engine/services/search_service.py   # + invalidate() + functional wrapper
packages/indexed-core/src/core/v1/engine/services/__init__.py         # export invalidate
packages/indexed-core/src/core/v1/config_models.py                    # MCPConfig.watch_enabled, watch_debounce_seconds
apps/indexed/src/indexed/mcp/reindex.py                               # NEW — ReindexManager, ReindexJob   ~180 LOC
apps/indexed/src/indexed/mcp/watcher.py                               # NEW — CollectionWatcher            ~120 LOC
apps/indexed/src/indexed/mcp/server.py                                # build_server() factory + lifespan wiring
apps/indexed/src/indexed/mcp/tools.py                                 # reindex tool + _get_manager
apps/indexed/src/indexed/mcp/resources.py                            # reindex block in collection status
apps/indexed/src/indexed/mcp/cli.py                                   # --no-watch flag → build_server(...)
tests/unit/indexed/mcp/                                               # manager, watcher, tool, cli tests
```

---

## Contract / API

```python
# core/v1/engine/services/search_service.py
class SearchService:
    def invalidate(self, collection_name: str | None = None) -> int:
        """Evict cached searcher(s). None → clear all. Returns count evicted.
        Cache keys are '{collection}:{indexer}', so a collection is matched by
        the '{collection}:' prefix across all its indexers."""

def invalidate(collection_name: str | None = None,
               collections_path: str | None = None) -> int: ...   # functional wrapper on the singleton

# apps/indexed/src/indexed/mcp/reindex.py
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
                 response_cache_clear: Callable[[], None] | None = None,  # None under the recommended Q1 option
                 collections_path: str | None = None) -> None: ...
    def schedule(self, collection: str) -> ReindexJob: ...   # idempotent, coalescing, non-blocking
    def status(self, collection: str | None = None) -> list[ReindexJob]: ...
    def latest(self, collection: str) -> ReindexJob | None: ...
    async def aclose(self) -> None: ...                      # cancel timers + await in-flight

# apps/indexed/src/indexed/mcp/watcher.py
class CollectionWatcher:
    def __init__(self, manager: ReindexManager, *, collections_path: str | None = None) -> None: ...
    def build_path_map(self) -> dict[Path, list[str]]: ...   # {resolved basePath: [collection names]}
    async def run(self, stop_event) -> None: ...             # awatch loop → manager.schedule
    def _keep(self, change, path: str) -> bool: ...          # watch_filter: drop excluded/gitignored/non-matching

# apps/indexed/src/indexed/mcp/server.py
@dataclass(frozen=True)
class WatchSettings:
    enabled: bool = True
    debounce_seconds: float = 3.0

def build_server(watch: WatchSettings | None = None) -> FastMCP: ...
mcp = build_server()   # default module-level instance for fastmcp.json / fastmcp_server.py re-export
```

```python
# reindex MCP tool (tools.py)
@mcp.tool
def reindex(collection: Optional[str] = None, ctx: Optional[Context] = None) -> Dict[str, Any]:
    """Background incremental re-index of one or all file collections.
    Returns {"accepted": [{"collection", "job_id", "state"}, ...]} immediately.
    Poll state via resource://collection/{name} (reindex block)."""
```

---

## Implementation Detail

**Re-index path.** `ReindexManager._run` calls
`core.v1.engine.services.update([SourceConfig(name=collection, type="localFiles",
base_url_or_path="", indexer=None)])` via `asyncio.to_thread` (blocking:
embeddings + model load). The update path keys off `name` only — `_update_one`
passes just `cfg.name` to `create_collection_updater`, which reconstructs indexer,
path, and type from the manifest; the other `SourceConfig` fields are inert here.
`update` → `update_collection_factory` already does the incremental localFiles
path (`ChangeTracker` + `state.json`, processes only changed files, computes
deletions, re-saves state). On success the manager calls
`search_invalidate(collection)` and handles the response cache (see § Open
Questions Q1), then records `documents_delta` / `chunks_delta`.

> **Delta read caveat.** The functional `status()` uses a process-global
> `InspectService` singleton whose `_manifest_cache` is never invalidated
> (`inspect_service.py:70-80,331-337`). Reading before/after counts through it
> would return the *same cached* manifest and report a zero delta. The manager
> MUST read after-counts from a **fresh** `InspectService(collections_path=…)`
> (or the manifest directly), not the cached singleton.

**Coalescing + serialization.** One `asyncio.Lock` per collection guards `_run`.
`schedule()` (re)arms a `debounce_seconds` timer per collection; if changes land
while a run is in flight, the collection is marked dirty and re-run exactly once
after. Two `schedule()` calls inside the window ⇒ one run.

**Watcher.** `build_path_map()` reads `status()` filtered to
`source_type == "localFiles"` and pulls `reader.basePath` from each
`manifest.json`. `run()` does `async for changes in awatch(*base_paths,
watch_filter=self._keep, stop_event=...)` (`awatch` is `recursive=True` by
default, so subtree adds are caught), maps each changed path to the collection(s)
whose base path contains it (`path.is_relative_to(base)` — nested roots may fan
out to several collections), and calls `manager.schedule(coll)`. If the path map
is empty (no file collections) the watcher idles and does **not** call `awatch`
(it rejects an empty path list).

`_keep` is a `watch_filter` — it runs **globally** across all watched roots, so it
cannot apply per-collection `includePatterns` precisely (a path may belong to
several collections with different patterns). It therefore does **coarse,
conservative** filtering only: extend `watchfiles.DefaultFilter` (which already
ignores `.git`, `node_modules`, `__pycache__`, `.venv`, editor swap/temp files)
with `connectors.files.schema.DEFAULT_EXCLUDED_DIRS`. Precise per-collection
include/gitignore filtering stays the `ChangeTracker`'s job at index time — `_keep`
only trims obvious churn before the debounce timer arms.

**Lifespan wiring.** `build_server` constructs the `ResponseCachingMiddleware`
once (configured per Q1 so `search`/`search_collection` stay fresh) and closes
over it for any cache hook the manager needs. `_make_lifespan` always builds
the `ReindexManager` (so the manual `reindex` tool works even under `--no-watch`)
and only starts `CollectionWatcher.run` when watching is enabled. `WatchSettings`
(from the CLI flag) overrides `MCPConfig`; precedence `--no-watch` > config >
default(true). On exit: `stop_event.set()` → `awatch` stops → `await
manager.aclose()`. `LifespanState` gains `reindex_manager: ReindexManager | None`.

**Tool + resource.** `reindex` reads the manager from `ctx.lifespan_context`
(same pattern as `resolve_config`), schedules the target(s), returns job stubs.
`resources._format_status` gains a `reindex` block populated from
`manager.latest(name)` when a manager is present.

<!-- merge -->
**Cross-cutting (promote to tech-core.md on COMPOUND):** `SearchService` gains a
public `invalidate(name)` so long-lived hosts (MCP server) can evict the
process-global searcher cache after content changes. Any future re-index/refresh
path — not just the watcher — must call it to avoid serving stale FAISS results.
<!-- /merge -->

## Performance Budget

- Watcher idle cost ≈ 0 (Rust `watchfiles` epoll/FSEvents; no polling).
- Re-index never runs on the event loop — `asyncio.to_thread` keeps `search`
  latency unaffected during indexing.
- Debounce default 3 s settle window; burst of N saves ⇒ 1 incremental run.

## Open Questions

1. **Response-cache strategy (resolved by investigation; decision pending).**
   Confirmed against fastmcp 3.2.4: `ResponseCachingMiddleware` caches `call_tool`
   by **default with a 1-hour TTL** — so `search` responses *do* go stale after a
   re-index. The middleware exposes **no** public `clear()`; its backend defaults
   to `MemoryStore` (an `AsyncKeyValue` with `delete` / `destroy_collection`), and
   the tool-cache key is per call-args. Two ways to stay fresh:
   - **(Recommended) Exclude search tools from tool caching** —
     `ResponseCachingMiddleware(call_tool_settings=CallToolSettings(excluded_tools=["search","search_collection"]))`.
     Freshness becomes structural; the manager only needs `SearchService.invalidate()`,
     no response-cache hook, no reaching into private internals. (Caching search on
     a server with a live watcher is arguably wrong anyway.)
   - **(Alternative) Imperative clear** — hold the backend store and call
     `destroy_collection(<tool-cache collection>)` on each re-index. Keeps tool
     caching but couples the manager to middleware internals.
   This revises the originally-locked "clear response cache" decision; see plan
   unit `file-watcher/1` and confirm direction before implementing.
2. **Mid-session collections.** Path map is built at startup; collections created
   later need a server restart. Periodic/triggered rebuild is a documented v2
   follow-up, not in scope here.
