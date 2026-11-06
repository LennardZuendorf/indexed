---
type: feature-plan
feature: file-watcher
sibling: tech.md
parent: ../../plan.md
updated: 2026-11-03
---

# Feature: File Watcher — Plan

**Parent:** [../../plan.md](../../plan.md) · **Product:** [product.md](product.md) · **Tech:** [tech.md](tech.md)

---

## Slices

| # | Slice | Gate | Status |
|---|-------|------|--------|
| 1 | Foreground `index watch <collection>`: polling, debounce coalescing, incremental update through the existing facade, vanished-path gate, `[watch]` cadence config, docs | live test proves a file edit changes collection content with no manual update; burst test proves one update per burst | ✅ DONE (this PR) |
| 2 | MCP integration: opt-in watcher in the server lifespan, `[mcp] watch_enabled` gate, per-collection treatment of collections created after startup | the MCP server serves fresh results for a `localFiles` collection without a restart | ⬜ NOT STARTED (separate card — needs the CLI watcher's semantics settled first) |
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
