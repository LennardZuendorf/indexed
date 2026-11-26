---
type: feature-tech
feature: project-search
sibling: product.md
parent: ../../tech.md
updated: 2026-11-26
---

# Feature: Project Search — Tech

**Sibling:** [product.md](product.md) · **Plan:** [plan.md](plan.md) ·
issue [#340](https://github.com/LennardZuendorf/indexed/issues/340).

## Where the source list comes from

A search knows two things: the **intended scope** (the workspace selection's
names, or the one name `--collection` asked for) and the **answered scope** (the
dict the engine returned for this query). Until now only the second reached the
payload.

`resolve_collections_context` already resolves `indexed.toml` into
`CliContext.selection` for every surface (CLI, LSP, MCP). The change is to keep
the entries that no longer resolve as *data* instead of aborting the whole
command:

- `WorkspaceSelection.unresolved: tuple[UnresolvedEntry, ...]` — one record per
  entry whose collection (or its data directory) is gone, carrying the entry,
  its name and the reason naming the file and the remedy.
- `resolve_entries(..., strict=...)`: malformed TOML, a missing or unsupported
  `version`, an empty `[collections].use` and a duplicate entry stay fatal
  (`WorkspaceSelectionError`) — those are broken files, not broken stores. With
  `strict=False` (CLI search, and the MCP context built at server start) an
  unresolvable entry lands in `unresolved`; with `strict=True` (LSP, storage,
  migration, every other CLI command) it raises exactly as before. MCP resolves
  non-strictly at lifespan because a dead collection must not stop the server
  from starting — otherwise its search could never degrade per source; the
  resources read the store and ignore the selection, so they are unaffected.

## The payload

`build_search_payload(raw_results, query, *, sources=None)` gains one optional
argument: the intended scope, already resolved into declarations by the caller
(`indexed.cli.search_sources.declare_sources`, shared by CLI and MCP, because
it needs `status()` and cannot live in the presentation layer):

```json
"sources": [
  {"collection": "indexed-issues", "source_type": "github",
   "status": "ok", "documents": 42, "hits": 3},
  {"collection": "indexed-wiki", "source_type": "localFiles",
   "status": "empty", "documents": 0,
   "error": "Collection 'indexed-wiki' indexes no documents ..."},
  {"collection": "indexed-code", "status": "missing",
   "error": "Workspace definition '/repo/indexed.toml' selects collection
             'indexed-code', which is not in the store at '...' ..."}
]
```

`status` precedence per declared source:

| observed | status |
|---|---|
| the engine returned `{"error": ...}` for it | `failed` (error = engine text) |
| an unresolved selection entry | `missing` |
| present but no indexers / unreadable manifest (`status()` omits it) | `unusable` |
| `status().number_of_documents == 0`, or the engine opened an index holding zero vectors | `empty` (error added, `documents` stated as 0) |
| otherwise answered | `ok` |

`hits` counts only what this query matched; `documents` is what the collection
indexes. Collections the engine returned but the caller never declared (e.g. an
explicit `--collection`) are appended as `ok`/`failed`, so `sources` is always a
superset of `collections`.

Every non-`ok` status also produces a `collection_errors` entry with the same
wording, so consumers that predate `sources` and both renderers (`index search`
human text, `--json`) keep naming the failure. `SEARCH_SCHEMA` stays
`indexed.search/1`: new key, no changed key, no changed meaning.

## CLI and MCP

- `index search` (no `--collection`) no longer exits 1 when a selected
  collection vanished: the resolvable statuses are searched, the dead entries
  become source declarations, exit stays 0. `--collection NAME` that cannot be
  searched keeps exiting 1 — an unanswered *request* is a failure.
- MCP `search` stops passing `configs=None`: it resolves the same
  `CliContext.selection`, searches the selected names (falling back to the whole
  store when there is no definition) and builds declarations the same way, so
  CLI and MCP answer the same scope with the same `sources`.
- `search_collection` declares its one collection, so a single-collection
  search also states whether it answered.

## Bounded detail and citable comments

The GitHub converter's `_comment_chunks` put each comment body into one
`indexedData` string — a 60 KB comment is one unbounded hit, which R5 forbids.
Comments now go through the same 512-token parser as issue bodies, and the
reader's GraphQL selection gains the comment `id` and `url`, carried as
`commentId`/`commentUrl` metadata. The payload then states, on each hit derived
from a comment, `url` = the comment's own URL, so a comment hit resolves to the
comment rather than to the issue. `Hit.url` is optional and only present when a
hit resolves to something narrower than its document.

R1's other half is the locator: `build_locator` now keeps a resolvable `path` on
`headings` and `document` locators, not only on `line_span`/`page`. Without it a
Markdown wiki hit carried only a heading path and the document kept its `file://`
url, so there was no `path` to hoist and a consumer had to parse the url; with it
the payload hoists `path` to the document and drops the url that only restated it.

## Evidence

`tests/unit/indexed/mcp/test_source_status_payload.py` (builder contract),
`tests/unit/indexed/knowledge/commands/test_search.py::TestWorkspaceSelectionScope`
(degrade, exit code), `tests/system/test_project_search_sources.py` (three real
seeded collections, one deleted, one emptied, byte budget) and
`tests/unit/indexed/mcp/test_search_payload_golden.py` (shape, both surfaces).
