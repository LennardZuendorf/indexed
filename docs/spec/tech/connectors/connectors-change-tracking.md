---
type: tech
updated: 2026-11-22
applies: "src/indexed/connectors/**"
---

# Change Tracking

`FileSystemConnector` supports incremental indexing via `ChangeTracker`:

| Strategy | Detection |
|----------|-----------|
| **git** | `git diff --name-status` between commits |
| **content-hash** | xxhash of contents vs stored state |
| **mtime** | modification time (faster, less reliable) |
| **auto** | git if `.git` exists, else content-hash |

State persisted as `state.json`, updated after each successful run.

**Correctness:** the git strategy is **content-hash-authoritative** — it reconciles
the diff against stored content hashes, so a file edited and then **reverted back to
its committed state** is still re-indexed (a name-status diff alone would miss it).
Git **C-quoted non-ASCII paths** (`"\303\244…"`) are unquoted to real filenames
before tracking.
