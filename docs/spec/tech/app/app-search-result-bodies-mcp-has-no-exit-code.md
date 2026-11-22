---
type: tech
updated: 2026-11-22
applies: ["src/indexed/mcp/**", "src/indexed/cli/**"]
---

# The two bodies: success and failure: MCP has no exit code

- **MCP has no exit code, and one of its bodies has no `type`.** `search_collection`
  answers an unknown name with the bare `{"error"}` its clients already match on
  (`mcp/collection_errors.py`) and reserves `type` for *present but unusable* — an
  agent must check `schema` first; on an error body, absence of `type` identifies
  this unknown-name case. Caught `IndexedError` instances preserve their concrete
  class as `type`; unexpected search/status failures use `MCPError`.
- **The empty store is a CLI envelope but an MCP success payload.** The CLI says
  `{"error": "No collections found"}`, the MCP tool returns the success shape with
  `collections: []`. Empty `collections` means no collection was searched (nothing
  exists, or nothing was searchable); inspect `collection_errors` to distinguish an
  empty store from all searches failing. Empty `documents` with non-empty
  `collections` means those collections matched nothing.
- **The CLI pre-validates `--changed-since`; MCP does not.** Before searching, the
  CLI resolves the ref against every collection it is about to search and treats an
  unresolvable one as fatal, whether or not `-c` named a collection
  (`_changed_since_problems` in `cli/knowledge/commands/search.py`); the MCP tools
  reach the engine with the ref unvalidated, so the same request returns a success
  payload with the collection in both arrays, rows unfiltered. Never infer "the ref
  is valid" from an MCP success payload.

**Errors that escape the command** (`ConfigurationError`, `StorageError`, … raised
before a payload exists) go to the CLI's top-level handler. It prints a Rich error
panel to **stdout** and exits with the mapped code (`1`, `2` for config, `3` for
storage). This exceptional stdout is not JSON. Check the exit code before parsing
stdout; a non-zero exit is a failed request. An `error` body reports a failure or
an empty store, while empty `collections` means no collection was searched.
`collection_errors` lists requests that were not carried out as asked: failed
collections (absent from `collections`) and skipped per-collection Git options
(present in `collections`, rows unfiltered).
The search bodies above are pinned:
`tests/unit/indexed/mcp/test_search_payload_golden.py` (CLI and MCP envelopes),
`tests/unit/indexed/mcp/test_tools_collection_errors.py` (unknown vs unusable
collection) and `tests/unit/indexed/knowledge/commands/test_search.py` (the CLI
`{"error": "No searchable collections available"}` rows, exit codes included).
