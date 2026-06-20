---
type: feature-tech
feature: file-watcher
sibling: product.md
parent: ../../tech.md
updated: 2026-06-20
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
                 response_cache_clear: Callable[[], None],
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

**Re-index path.** `ReindexManager._run` builds a minimal `SourceConfig(name,
type="localFiles", base_url_or_path="", indexer=<from status>)` and calls
`core.v1.engine.services.update([src])` via `asyncio.to_thread` (blocking:
embeddings + model load). `update` → `update_collection_factory` already does the
incremental localFiles path (`ChangeTracker` + `state.json`, processes only
changed files, computes deletions, re-saves state). On success the manager calls
`search_invalidate(collection)` and `response_cache_clear()`, then records
`documents_delta` / `chunks_delta` from `status()` before/after.

**Coalescing + serialization.** One `asyncio.Lock` per collection guards `_run`.
`schedule()` (re)arms a `debounce_seconds` timer per collection; if changes land
while a run is in flight, the collection is marked dirty and re-run exactly once
after. Two `schedule()` calls inside the window ⇒ one run.

**Watcher.** `build_path_map()` reads `status()` filtered to
`source_type == "localFiles"` and pulls `reader.basePath` from each
`manifest.json`. `run()` does `async for changes in awatch(*base_paths,
watch_filter=self._keep, stop_event=...)`, maps each changed path to the
collection(s) whose base path contains it (`path.is_relative_to(base)` — nested
roots may fan out to several collections), and calls `manager.schedule(coll)`.
`_keep` drops events under `connectors.files.schema.DEFAULT_EXCLUDED_DIRS`,
gitignored paths, and non-matching `includePatterns` to avoid debounce churn;
`ChangeTracker` remains the source of truth at index time.

**Lifespan wiring.** `build_server` constructs the `ResponseCachingMiddleware`
once and closes over it for `response_cache_clear`. `_make_lifespan` always builds
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

1. **Response-cache eviction API.** Confirm `fastmcp.server.middleware.caching.ResponseCachingMiddleware`
   exposes a public clear/evict. If not, the fallback is searcher-invalidation
   only plus a short middleware TTL. De-risked first (plan unit `file-watcher/1`).
2. **Mid-session collections.** Path map is built at startup; collections created
   later need a server restart. Periodic/triggered rebuild is a documented v2
   follow-up, not in scope here.
