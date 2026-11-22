---
type: tech
updated: 2026-11-22
applies: "src/indexed/mcp/**"
---

# Freshness & error envelopes

- **No response caching.** The server registers no response-caching middleware —
  a `search` after a re-index reflects the latest on-disk index (core's searcher
  cache already provides the latency win and invalidates on load).
- **Opt-in live freshness.** With `[mcp] watch_enabled = true` the lifespan
  starts one `run_watch_loop` thread per `localFiles` collection that exists at
  startup, so local edits reach search without a restart or a manual
  `index update`. The default is off: startup and behaviour are then unchanged.
  Collections created after startup are watched on the next restart (see
  [features/file-watcher/tech.md](../../features/file-watcher/tech.md) § MCP server
  wiring). The lifespan warms the parsing tokenizer before it starts those
  threads, so the first `transformers` import cannot race the first `search`
  (#335).
- **Failures are surfaced, never swallowed.** A per-collection failure is reported
  in `collection_errors` on the success payload, never dropped as a silent
  "0 matches"; the boundary envelopes **every** exception (core raises
  `IndexedError` for missing/corrupt collections) so the agent sees "index
  failed", not empty results.
