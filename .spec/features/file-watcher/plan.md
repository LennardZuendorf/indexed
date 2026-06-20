---
type: feature-plan
feature: file-watcher
sibling: tech.md
parent: ../../plan.md
updated: 2026-06-20
---

# Feature: MCP File Watcher — Implementation Plan

Delivers automatic, debounced re-indexing of `localFiles` collections during MCP
server runtime, plus an async `reindex` tool — built bottom-up: cache hook first,
then the manager, then the watcher, then server/tool/CLI wiring. A closed,
testable box layered on the existing `update` pipeline.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)
**Design:** [design.md](design.md)

**Feature gate:** Starts on top of Feature 7 (MCP server) and Feature 5 (File
system connector), both `DONE` in root [plan.md](../../plan.md) Feature Sequence.
Depends on no other feature's units.

---

## Problem Frame

The re-index logic already exists (`core.v1.engine.services.update` is incremental
for files). The work is the *runtime glue*: a long-lived watcher, a debouncing
job manager that runs indexing off the event loop, and — the one correctness
risk — invalidating the process-global searcher cache so a long-running server
never serves stale results. Build the cache hook and manager (pure asyncio,
mockable) before the filesystem-facing watcher and the FastMCP wiring.

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Automatic watching of file collections](product.md#requirement-automatic-watching-of-file-collections) | file-watcher/3, file-watcher/4 |
| R2 | [Opt-out control](product.md#requirement-opt-out-control) | file-watcher/4, file-watcher/6 |
| R3 | [Debounced, coalesced re-indexing](product.md#requirement-debounced-coalesced-re-indexing) | file-watcher/2 |
| R4 | [Fresh results after re-index](product.md#requirement-fresh-results-after-re-index) | file-watcher/1, file-watcher/2 |
| R5 | [Asynchronous re-index tool](product.md#requirement-asynchronous-re-index-tool) | file-watcher/5 |
| R6 | [Observable re-index status](product.md#requirement-observable-re-index-status) | file-watcher/5 |
| R7 | [Safe concurrency and transport hygiene](product.md#requirement-safe-concurrency-and-transport-hygiene) | file-watcher/2, file-watcher/3 |

---

## Key Technical Decisions

1. **`SearchService.invalidate()` + response-cache clear.** Evict the affected
   collection's cached searcher and bust the FastMCP response cache after each
   successful re-index — the key correctness fix. See [tech.md](tech.md) § Implementation Detail.
2. **`build_server()` factory.** Refactor the module-level server into a factory
   that accepts `WatchSettings`, so `--no-watch` reaches the lifespan cleanly while
   `fastmcp.json` / `fastmcp_server.py` keep using a default-built `mcp`.
3. **One `reindex(collection?)` tool; status via existing resource.** No separate
   status tool — `resource://collection/{name}` carries a `reindex` block.
4. **`watchfiles` (already installed).** Asyncio-native `awatch` with built-in
   debounce + `watch_filter`; no new dependency, no polling.
5. **Manager always built; only the watcher honours `--no-watch`.** Manual
   `reindex` stays available even when the auto-watcher is off.

---

## Unit IDs

Units are `file-watcher/n`, assigned once and never renumbered. Cite IDs in
commits and tests (`feat(mcp): file-watcher/3 ...`).

---

### file-watcher/1 — Search cache invalidation hook

**Goal:** `SearchService` can evict a collection's cached searcher; manual spike confirms the response-cache clear path.

**Requirements:** R4

**Dependencies:** —

**Files:**

```
packages/indexed-core/src/core/v1/engine/services/search_service.py   # add invalidate() + wrapper
packages/indexed-core/src/core/v1/engine/services/__init__.py         # export invalidate
```

**Test scenarios:**

- Seeding the cache then `invalidate("docs")` evicts all `docs:*` keys and returns the count
- `invalidate(None)` clears the whole cache
- Spike: confirm `ResponseCachingMiddleware` exposes a clear/evict hook (or settle the fallback)

**Verification:** `uv run pytest tests/unit/indexed_core/ -q -k invalidate`; documented spike result in [tech.md](tech.md) § Open Questions.

---

### file-watcher/2 — ReindexManager (debounce, coalesce, off-loop run)

**Goal:** A job manager that schedules, debounces, serializes per collection, runs `update()` in a thread, and invalidates caches on success.

**Requirements:** R3, R4, R7

**Dependencies:** file-watcher/1

**Files:**

```
apps/indexed/src/indexed/mcp/reindex.py        # ReindexManager, ReindexJob
```

**Test scenarios:**

- Two `schedule()` calls within the window → exactly one `update` call (mocked)
- Per-collection lock serializes overlapping runs; mid-run change re-runs once
- Success → `search_invalidate` + `response_cache_clear` called; deltas recorded
- `update` raises → job `error`, manager stays healthy; `aclose()` cancels cleanly

**Verification:** `uv run pytest tests/unit/indexed/mcp/test_reindex_manager.py -q`.

---

### file-watcher/3 — CollectionWatcher over watchfiles

**Goal:** Map `localFiles` base paths → collections and drive the manager from `awatch`, with noise filtering.

**Requirements:** R1, R7

**Dependencies:** file-watcher/2

**Files:**

```
apps/indexed/src/indexed/mcp/watcher.py        # CollectionWatcher
```

**Test scenarios:**

- `build_path_map` resolves base paths from status + manifests, incl. nested roots
- Monkeypatched `awatch` yielding synthetic changes → correct `schedule()` calls
- `_keep` drops excluded dirs / gitignored / non-matching patterns

**Verification:** `uv run pytest tests/unit/indexed/mcp/test_watcher.py -q`.

---

### file-watcher/4 — Server factory + lifespan wiring + config

**Goal:** `build_server(WatchSettings)`, lifespan starts/stops watcher + manager, `MCPConfig` gains watch keys.

**Requirements:** R1, R2

**Dependencies:** file-watcher/2, file-watcher/3

**Files:**

```
apps/indexed/src/indexed/mcp/server.py         # build_server, _make_lifespan, LifespanState field
packages/indexed-core/src/core/v1/config_models.py   # watch_enabled, watch_debounce_seconds
```

**Test scenarios:**

- `build_server(WatchSettings(enabled=False))` → lifespan starts no watcher task
- Manager built regardless of `enabled` (manual reindex still works)
- Clean cancel on lifespan exit (no pending tasks)

**Verification:** `uv run pytest tests/unit/indexed/mcp/test_server_lifespan.py -q`; `uv run indexed mcp inspect`.

---

### file-watcher/5 — reindex tool + status resource

**Goal:** `reindex(collection?)` schedules background work and returns job stubs; collection status resource reports re-index state.

**Requirements:** R5, R6

**Dependencies:** file-watcher/4

**Files:**

```
apps/indexed/src/indexed/mcp/tools.py          # reindex tool + _get_manager
apps/indexed/src/indexed/mcp/resources.py      # reindex block in _format_status
```

**Test scenarios:**

- `reindex("docs")` returns a job id + accepted collection without blocking
- `reindex()` targets all file collections
- No manager (disabled) → clear error; `resource://collection/docs` shows reindex state

**Verification:** `uv run pytest tests/unit/indexed/mcp/test_reindex_tool.py -q`.

---

### file-watcher/6 — CLI --no-watch flag

**Goal:** Thread `--no-watch` from `mcp run` into `build_server(WatchSettings(...))`.

**Requirements:** R2

**Dependencies:** file-watcher/4

**Files:**

```
apps/indexed/src/indexed/mcp/cli.py            # --no-watch option + run_impl wiring
```

**Test scenarios:**

- `mcp run --no-watch` builds a server with the watcher disabled (spy on `build_server`)
- Default `mcp run` builds with watching enabled

**Verification:** `uv run pytest tests/unit/indexed/mcp/test_cli_watch_flag.py -q`.

---

## Progress

| Unit | Status |
|---|---|
| file-watcher/1 | NOT STARTED |
| file-watcher/2 | NOT STARTED |
| file-watcher/3 | NOT STARTED |
| file-watcher/4 | NOT STARTED |
| file-watcher/5 | NOT STARTED |
| file-watcher/6 | NOT STARTED |

---

## Open Questions

1. **Response-cache eviction API** (`file-watcher/1` spike) — if no public hook
   exists, fall back to searcher-invalidation + short middleware TTL. Recommendation: prefer the public hook; fallback is acceptable for v1.
