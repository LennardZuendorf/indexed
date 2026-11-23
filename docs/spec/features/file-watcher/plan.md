---
type: feature-plan
feature: file-watcher
sibling: tech.md
parent: ../../plan.md
updated: 2026-11-16
---

# Feature: File Watcher — Plan

**Parent:** [../../plan.md](../../plan.md) · **Product:** [product.md](product.md) · **Tech:** [tech.md](tech.md)

---

## Slices

| # | Slice | Gate | Status |
|---|-------|------|--------|
| 1 | Foreground `index watch <collection>`: polling, debounce coalescing, incremental update through the existing facade, vanished-path gate, `[watch]` cadence config, docs | live test proves a file edit changes collection content with no manual update; burst test proves one update per burst | ✅ DONE (PR #278) |
| 2 | MCP integration: opt-in watcher in the server lifespan, `[mcp] watch_enabled` gate, per-collection treatment of collections created after startup | the MCP server serves fresh results for a `localFiles` collection without a restart | ✅ DONE (this PR) |
| 3 | Git-hook triggered reindexing | a `post-commit` hook install/reinstall/uninstall that is append-safe | ⬜ NOT STARTED (still an explicit scope decision, per issue #67) |

## Dependencies

- Issue #112 criterion 4 (CLI/MCP storage parity) — landed.
- Issue #126 write-publication contract (#244) — landed; slice 1 relies on
  build-aside + atomic swap and must not sweep strands.

## Evidence for slice 1

| Requirement | Proof |
|---|---|
| live edit changes collection content, no manual update | `tests/system/test_watch_live_edit.py` |
| no rebuild storm on a burst | `tests/unit/indexed/knowledge/commands/test_watch.py::test_burst_of_changes_runs_exactly_one_update` |
| documented failure mode when the watched path disappears | `test_missing_source_path_blocks_the_update_and_resumes` + [product.md](product.md) § Failure behaviour |
| opt-in, no daemon, cold start unchanged | command is the only entry point; `watch_service` is imported inside the command body; `tests/unit/test_import_chain.py` stays green |

## Evidence for slice 2

| Requirement | Proof |
|---|---|
| a served `localFiles` collection returns fresh results after a source edit, no restart, no manual update | `tests/system/test_mcp_watch_freshness.py::test_live_edit_becomes_searchable_without_a_restart` (out-of-process stdio server) |
| `watch_enabled=false` starts no watcher and leaves startup cost unchanged | `tests/unit/indexed/mcp/test_watch.py::test_gate_off_starts_nothing_and_imports_no_watcher` + `test_lifespan_with_gate_off_never_imports_the_watcher`; gate-off live control in `test_gate_off_watches_nothing_and_scope_is_fixed_at_startup` |
| collections created after startup are defined and tested | plan-once unit test (`test_startup_scope_is_fixed_and_stop_joins_the_threads`) + live negative control and restart pickup in the system test; [product.md](product.md) § MCP server mode |
| missing source path is never an update | `watch_service.resolve_watch_target` returns `None` before a thread starts (skipped with a warning); `test_missing_source_directory_is_never_a_signature` |
| reuse `signature_for`/`run_watch_loop`, no fork | `mcp/watch.py` calls `run_watch_loop`; both CLI and MCP scan through `WatchTarget.scan()` |
| clean shutdown on lifespan exit | `WatcherHandle.stop()` sets the shared event and joins the tasks; `test_startup_scope_is_fixed_and_stop_joins_the_threads` + the system test's session close |
| docs: on/off and new-collection behaviour | [product.md](product.md) § MCP server mode, [../../tech/config/README.md](../../tech/config/README.md) `[mcp]`, README § Watching a collection |
