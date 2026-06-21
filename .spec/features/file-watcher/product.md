---
type: feature-product
feature: file-watcher
sibling: tech.md
parent: ../../product.md
updated: 2026-06-21
---

# Feature: MCP File Watcher — Product

Keeps `localFiles` collections fresh automatically while the MCP server runs. The
server watches the folders backing file collections and, after a short debounce,
runs an incremental re-index when files are added, modified, or deleted — so AI
agents always search current content without anyone running `index update` by
hand. A companion MCP tool lets an agent trigger the same re-index on demand,
asynchronously. The feature also closes the **stale-collection** gap that made
this necessary: a long-running server now reflects on-disk reality — fresh
counts, fresh search, explicit errors for broken collections, and pickup of
collections created after startup — whether the change came from the watcher or
an external `index update`.

**Tracks:** GitHub [#67](https://github.com/LennardZuendorf/indexed/issues/67)
(automatic re-indexing — file-watching half) and
[#112](https://github.com/LennardZuendorf/indexed/issues/112) (MCP server serves
stale collections).

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Design:** [design.md](design.md)
**Plan:** [plan.md](plan.md)
**Discovery:** [research.md](research.md)

---

## Scope

| | |
|---|---|
| **Owns** | The watcher lifecycle inside the MCP server, the debounce/coalescing policy, the `reindex` MCP tool, the `--no-watch` flag, the `[mcp]` watch config keys, the search-cache invalidation hook, **collection-metadata cache coherence** (mtime-aware manifest reads so status/search reflect on-disk changes), **explicit surfacing of collection load failures** in the search tools, and **discovery of collections created after startup**. |
| **Does not own** | The indexing/update pipeline itself (core `update` service), file change detection (`ChangeTracker` in connectors), the FAISS search algorithm, non-file connectors, and how collections are created. The feature *consumes* these; beyond the manifest-cache coherence fix it does not change their behaviour. |

---

## Requirements

### Requirement: Automatic watching of file collections

The system SHALL, while the MCP server is running, watch the folders that back
every `localFiles` collection and trigger a re-index of the affected collection
when files in those folders change. Watching MUST be active by default.

#### Scenario: File added to a watched folder

- **Given** the MCP server is running with a `localFiles` collection rooted at `./docs`
- **When** a new file `./docs/guide.md` is created and the debounce window elapses
- **Then** the collection is incrementally re-indexed and a subsequent `search` returns content from `guide.md`

#### Scenario: File deleted from a watched folder

- **Given** a watched collection that already indexed `./docs/old.md`
- **When** `./docs/old.md` is removed and the debounce window elapses
- **Then** the collection is re-indexed and `search` no longer returns chunks from `old.md`

### Requirement: Opt-out control

The system SHALL let the operator disable the automatic watcher via a
`--no-watch` flag on `mcp run` and via an `[mcp].watch_enabled` config key, with
the flag taking precedence over config.

#### Scenario: Watcher disabled by flag

- **Given** the operator starts the server with `indexed mcp run --no-watch`
- **When** files change in a folder backing a collection
- **Then** no automatic re-index is triggered

### Requirement: Debounced, coalesced re-indexing

The system SHALL wait a configurable settle window after the last observed change
before re-indexing, and MUST collapse a burst of changes to one collection into a
single re-index run.

#### Scenario: Burst of edits collapses to one run

- **Given** a watched collection
- **When** ten files are saved within the settle window
- **Then** exactly one incremental re-index runs for that collection after the window

### Requirement: Fresh results after re-index

The system SHALL invalidate cached search state for a collection after it is
re-indexed so that subsequent searches never return stale results from the
pre-re-index index.

#### Scenario: Search reflects re-indexed content

- **Given** a collection was searched once (warming the in-memory searcher cache)
- **When** its source files change and the collection is re-indexed
- **Then** the next `search` reflects the new content, not the cached pre-change index

### Requirement: Asynchronous re-index tool

The system SHALL expose an MCP tool that triggers a background re-index of one or
all file collections and returns immediately with a job identifier rather than
blocking until indexing completes.

#### Scenario: Agent triggers a background re-index

- **Given** an agent connected to the MCP server
- **When** the agent calls `reindex(collection="docs")`
- **Then** the call returns promptly with a job id and accepted collection, and the re-index proceeds in the background

### Requirement: Observable re-index status

The system SHALL make the state of the most recent re-index for a collection
observable through the existing collection status resource.

#### Scenario: Agent polls re-index state

- **Given** a re-index was triggered for `docs`
- **When** the agent reads `resource://collection/docs`
- **Then** the response includes the current re-index state (e.g. `running` then `done`)

### Requirement: Safe concurrency and transport hygiene

The system SHALL serialize re-indexing per collection so two runs never overlap
for the same collection, and MUST NOT emit watcher logs onto the stdio MCP
channel.

#### Scenario: Overlapping triggers serialize

- **Given** a re-index for `docs` is in progress
- **When** another change for `docs` arrives
- **Then** the second run does not start until the first finishes, and is coalesced into a single follow-up run

### Requirement: Coherent metadata after on-disk changes

The system SHALL ensure collection status and search reflect the current on-disk
state of a collection after it changes — whether re-indexed by the watcher or by
an external `index update` — rather than a snapshot cached at process start. A
long-lived process MUST detect a replaced `manifest.json` and reload it.

#### Scenario: External re-index reflected in status

- **Given** a running MCP server that has reported `docs` at 50 documents
- **When** `docs` is rebuilt on disk to 320 documents (e.g. `indexed index update docs` in another terminal)
- **Then** `resource://collections/status` reports 320 documents without a server restart

### Requirement: Explicit surfacing of load failures

The system SHALL return an explicit error for a collection that exists on disk but
whose index fails to load, and MUST NOT silently return an empty result set or
silently drop the collection from an all-collections search.

#### Scenario: Unreadable collection surfaces an error

- **Given** a collection `docs` exists on disk but its index is corrupt/unreadable
- **When** an agent calls `search_collection(collection="docs", query=…)`
- **Then** the response contains an explicit error, not an empty result set

#### Scenario: All-collections search reports the failure

- **Given** `docs` fails to load while other collections are healthy
- **When** the agent calls `search(query=…)`
- **Then** the healthy collections return results and `docs` is reported as a warning, not silently omitted

### Requirement: Newly created collections without restart

The system SHALL make a collection created after the server started searchable and
visible in collection status without a server restart.

#### Scenario: Collection created after startup is searchable

- **Given** the MCP server started with collections `{a, b}`
- **When** a new collection `c` is created on disk
- **Then** `search_collection(collection="c", query=…)` returns results and `c` appears in `resource://collections/status`, without a restart

---

## User Experience

Operators get fresh search with zero manual upkeep. Starting the server is
unchanged; the watcher runs silently in the background. Opting out is one flag.

```
$ indexed mcp run
# ... server starts, watcher active for all localFiles collections ...

$ indexed mcp run --no-watch        # automatic watcher off; manual reindex tool still available
```

Agents can force a refresh and observe it:

```
reindex(collection="docs")
→ {"accepted": [{"collection": "docs", "job_id": "rdx_01H…", "state": "queued"}]}

resource://collection/docs
→ { …, "reindex": {"state": "done", "job_id": "rdx_01H…", "documents_delta": 1} }
```

## Non-Goals

- Watching non-file connectors (Jira/Confluence/Outline) — those have no local folder to watch.
- Live file-*watching* of collections created after startup — they become searchable and visible in status immediately, but auto re-index on *their* file changes still needs a restart (v2; see [tech.md](tech.md) § Open Questions).
- **Git-hook / commit-time re-indexing** (the second half of [#67](https://github.com/LennardZuendorf/indexed/issues/67)) — the always-on watcher supersedes it for the MCP scenario. Revisit as a standalone issue only if daemon-free, commit-boundary freshness (fresh index with no server running) is ever needed.
- A full job history/audit log — only the latest re-index per collection is reported.
- Replacing the `indexed index update` CLI command.
- CLI-side staleness work — `indexed` commands are short-lived processes that read manifests fresh per invocation, so they never serve a stale cache; the metadata-coherence fix lives in core and benefits any long-lived consumer regardless.

## Open Questions

_None blocking — all design decisions resolved in [plan.md](plan.md) § Key
Technical Decisions and [tech.md](tech.md) § Open Questions._
