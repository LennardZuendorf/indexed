---
type: feature-tech
feature: file-watcher
sibling: product.md
parent: ../../tech.md
updated: 2026-11-22
---

# Feature: File Watcher — Architecture

A foreground polling loop in the CLI layer that reuses the existing update path
unchanged. The watcher owns *when*, never *how*: it calls the same
`core.engine.update` the `index update` command calls, so delta detection,
per-document content-hash skip, build-aside staging and the atomic rename swap
all stay in one place.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)
**App spec:** [../../tech/app/README.md](../../tech/app/README.md) · **Config:** [../../tech/config/README.md](../../tech/config/README.md)

---

## Shape

| Layer | File | Role |
|---|---|---|
| Command | `cli/knowledge/commands/watch.py` | resolve collection + manifest reader config, validate, run the loop |
| Service | `cli/knowledge/commands/watch_service.py` | `WatchTarget` (resolved scope), tree fingerprint, exclusion walk, `run_watch_loop` |
| Config | `cli/watch_config.py` | `[watch] debounce_seconds`, `poll_interval_seconds` |
| MCP | `mcp/watch.py` | lifespan-scoped supervisor: plan once at startup, one thread per collection |

Registered as `index watch` (plus the flat hidden alias `watch`) in
`cli/_app_setup.py` and `cli/knowledge/cli.py`; the model is registered at
`register_app_config` (path `watch`), never at import time.

## MCP server wiring (slice 2)

`FastMCP`'s `lifespan` (`mcp/server.py`) is the only hook. After config
resolution it checks `[mcp] watch_enabled`; when false the branch ends at one
attribute read — `mcp/watch.py`, the engine and `watch_service` are all imported
*inside* the enabled branch, so a default server's cold start and behaviour are
untouched (the CLI's <1s start never touches this path at all).

When true, `mcp/watch.py`:

1. plans **once**: `core.engine.status(collections_path=...)`, keep
   `source_type == "localFiles"` entries with an indexer, and
   `watch_service.resolve_watch_target` each one. A non-directory source is
   skipped with a warning — same data-loss gate, applied before any thread
   exists;
2. starts one `asyncio.to_thread(run_watch_loop)` per collection, sharing one
   `threading.Event` as the stop signal, so the blocking update never runs on
   the event loop;
3. on lifespan exit sets the event and `await`s the tasks. The loops notice the
   event on their next poll tick or at the end of an in-flight update, so a
   shutdown never abandons a half-written collection.

Before step 2 the lifespan calls `parsing._model_window.prewarm_tokenizer()`
(#335). The catch-up update parses files in its worker thread and the first
`search` loads the embedder on the main thread; both need `transformers`, and
losing that first-import race used to cache a tokenizer-less chunker for the
whole process (every chunk sized by `len(text) // 3`). Warming the tokenizer
before any watcher exists makes the import order structural, not lucky. With
the gate off the branch is still one attribute read — no warming, no import.

The tokenizer warm-up covers one module, not the whole update path, and the
first `search` is not the only other importer: FastMCP runs each sync tool on
its own thread, so the *search handler* can be importing `llama_index` at the
same moment as a catch-up pass. `watch.warm_shared_stack()` therefore runs
inside `start_watchers_if_enabled`, synchronously, **before the first watcher
task is created**: from then on `sys.modules` is populated, and no thread —
watcher or tool — can observe a half-built module. Warming from inside the
first pass (as #361 did, under a `threading.Lock`) serialised the watchers
against each other but not against the tool thread, so the search handler still
lost the import and reported `cannot import name 'BaseEmbedding' from partially
initialized module 'llama_index.core.base.embeddings.base'`, or deadlocked on
`_ModuleLock` with two collections. A half-initialised module stays in
`sys.modules` and fails every later call in that process, which the macOS
system test saw as a restart that never caught up.

The warm-up imports `llama_index.embeddings.huggingface`, the module that logged
the partially initialized `BaseEmbedding`, which pulls `llama_index.core`,
`transformers` and `sentence-transformers` — the cold stack of both engines.
It is an optimisation, never a failure mode: a failed warm-up logs one warning
and each pass then imports the stack itself, where a broken install surfaces.
Its cost is paid at startup (the lifespan has not yielded, so no tool is served
yet), not on the first search.

The plan is not re-run while the server lives: collections created after
startup are watched only after the next restart (documented in
[product.md](product.md) § MCP server mode). Each loop's `apply_update` is the
same `clear_overlay()` + `core.engine.update([SourceConfig], manifest_factory=
wiring_kwargs_for_update(cli_ctx))` the CLI watcher runs, with
`collections_path` pinned to the lifespan's `cli_context.collections_path` so
the watcher can only ever write the store the tools read. A loop ending non-zero
(three consecutive update failures, vanished source) is logged and leaves the
server serving the last good index — it never takes the server down.

## Why polling, not inotify

- No new runtime dependency, so no `uv.lock` churn and no CLI cold-start cost
  (the service module is imported *inside* the command body, mirroring
  `update.py`).
- Works where events do not: network mounts, containers, some CI filesystems.
- The scan is a **wake-up signal only**. A false positive costs one update pass
  that finds no delta and returns a timestamp-only manifest bump — never a
  rebuild. A false negative is the only real risk, which is why the fingerprint
  errs toward over-reporting: include/negation patterns are not mirrored, so a
  file the reader would skip can still wake the loop.

## Fingerprint and burst coalescing

`signature_for(base_path)` returns `(files, blake2b(path,size,mtime_ns over the
sorted watched set))`, or `None` when the base path is not a directory. The walk
prunes the reader's configured directory exclusions, or `DEFAULT_EXCLUDED_DIRS` when none are configured, and
per-directory `.gitignore` specs and the resolved active storage root, so ignored files and storage writes do not wake updates. If the source is the storage root, its data directory is excluded.

`run_watch_loop` runs an initial update using the initial signature, then polls.
It records the pre-update signature rather than a later scan, so edits during an
update trigger a follow-up. Failed updates retry after a poll and quiet debounce
period even without a new edit. On a signature change it waits for a full quiet
`debounce_seconds` (each further change pushes the deadline out) before running
**one** update. It is fully injectable (`scan`, `apply_update`, `clock`,
`sleep`, `stop`) so the burst/failure semantics are unit-tested without waiting.

## Write contract (must not be broken)

- **Single writer per collection by contract.** There is no lock in the store;
  `replace_dir` publishes atomically, so a second concurrent writer's work is
  silently lost (last swap wins). The watcher never starts a second pass while
  one is running, and it never claims exclusivity it does not have.
- **Never sweep strands.** `.tmp-*`/`.trash-*` siblings belong to
  `core/recovery.py` (`recover_stranded`), which needs pid liveness to decide.
- **A missing canonical directory is transient**, not a deletion: the swap
  window renames the collection dir away before renaming the new one in.
- **The data-loss gate is the feature's spine**: `signature_for` returns `None`
  for a missing base path and the loop refuses to call `update`, because the
  files reader walks a nonexistent path silently (`os.walk` yields nothing),
  which the change tracker would classify as "every file deleted". Reader inventory traversal raises on filesystem errors or a replaced source root, closing the gap between the last watcher scan and enumeration.

## Evidence

- `tests/unit/indexed/knowledge/commands/test_watch.py` — burst coalescing
  (5 changes → 1 update), quiet tree (0 updates), vanished path (0 updates, one
  error, resumes), 3 consecutive failures → exit 1, gitignore/excluded-dir
  fingerprints, `--once`, refusals.
- `tests/system/test_watch_live_edit.py` — real corpus, real files connector,
  real v2 ingestion (embedding mocked): a file written while the loop runs
  becomes a document and is searchable, with no manual `index update`.
- `tests/system/test_mcp_watch_freshness.py` — out-of-process stdio server with
  `[mcp] watch_enabled = true`: a file written after startup is searchable
  through the same session (no restart, no manual update); with the gate off a
  live edit is not picked up and a collection created mid-run stays outside the
  scope until the next server start.
- `tests/unit/indexed/mcp/test_watch.py` — gate off imports no watcher module
  and starts no thread; the plan covers `localFiles` only and skips
  missing/unindexable sources; the plan runs exactly once per start; stop joins
  the threads; `resolve_watch_target(...).scan()` is `None` once the source
  directory disappears; with the gate on the tokenizer warm-up precedes
  `start_watchers_if_enabled` and the serving window (#335); the cold stack is
  warmed exactly once, no pass starts before it, a failed warm-up and a failed
  collection both leave the other collections running (#358).
