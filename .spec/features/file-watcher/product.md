---
type: feature-product
feature: file-watcher
sibling: tech.md
parent: ../../product.md
updated: 2026-06-20
---

# Feature: MCP File Watcher — Product

Keeps `localFiles` collections fresh automatically while the MCP server runs. The
server watches the folders backing file collections and, after a short debounce,
runs an incremental re-index when files are added, modified, or deleted — so AI
agents always search current content without anyone running `index update` by
hand. A companion MCP tool lets an agent trigger the same re-index on demand,
asynchronously.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Design:** [design.md](design.md)
**Plan:** [plan.md](plan.md)
**Discovery:** [research.md](research.md)

---

## Scope

| | |
|---|---|
| **Owns** | The watcher lifecycle inside the MCP server, the debounce/coalescing policy, the `reindex` MCP tool, the `--no-watch` flag, the `[mcp]` watch config keys, and the search-cache invalidation hook that keeps results fresh after a re-index. |
| **Does not own** | The indexing/update pipeline itself (core `update` service), file change detection (`ChangeTracker` in connectors), the search algorithm, non-file connectors, and how collections are created. The feature *consumes* these; it does not modify their behaviour. |

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
- Picking up collections created *after* the server started (requires restart in v1).
- A full job history/audit log — only the latest re-index per collection is reported.
- Replacing the `indexed index update` CLI command.

## Open Questions

_None blocking — all design decisions resolved in [plan.md](plan.md) § Key
Technical Decisions and [tech.md](tech.md) § Open Questions._
