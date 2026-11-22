---
type: tech
updated: 2026-11-22
applies: ["src/indexed/mcp/**", "src/indexed/cli/**"]
---

# The two bodies: success and failure

CLI consumers check exit status before parsing stdout; non-zero responses may be
non-JSON. For exit-zero JSON and MCP results, read `schema` first:

- **`schema` present** → the success shape documented above. Empty `documents`
  means no matched content was returned. `collections` lists searched collections
  (a collection whose requested option was skipped is listed: its rows came back
  unfiltered, and it also carries a `collection_errors` entry). Empty
  `collections` means **no collection was searched**; inspect `collection_errors`
  to distinguish an empty store from all searches failing. Non-empty `collections`
  with empty `documents` means those collections matched nothing.
- **`schema` absent** → an error envelope, `error` holding the message. A request that
  failed never reads as "nothing matched".

| Surface | Body | Exit |
|---|---|---|
| CLI `search --json -c <name>` — collection unknown or omitted by status after an unreadable manifest | `{"error": "Collection 'x' not found"}` | `1` |
| CLI `search --json -c <name>` — known status with no indexers | `{"error": "No searchable collections available"}` | `1` |
| CLI `search --json` (all) — no collections exist | `{"error": "No collections found"}` | `0` |
| CLI `search --json` (all) — collections exist, none searchable | `{"error": "No searchable collections available"}` | `0` |
| MCP `search` — empty store | *success* payload, `collections: []`, `documents: []`, `counts` zeroed | n/a (tool result) |
| CLI `search --json` / MCP `search` — one collection fails, others answer | success payload with that collection in `collection_errors`, absent from `collections` | CLI `0`; MCP n/a |
| CLI `search --json` (all collections) — a requested Git option cannot apply to one of them (v1 engine, no Git repository behind it) | success payload with that collection in **both** `collections` and `collection_errors`, its rows returned unfiltered/unranked | `0` |
| MCP `search` / `search_collection` — same, plus a `changed_since` ref that does not resolve (MCP has no ref pre-check) | success payload with the collection in **both** `collections` and `collection_errors`, its rows returned unfiltered/unranked | n/a (tool result) |
| CLI `search --json -c <name>` — `--changed-since <ref>` requested on a named collection that cannot carry the filter (v1 engine, not inside a Git repository, no files reader) | `{"error": "--changed-since '<ref>' cannot be applied: collection '<name>' uses the v1 engine (git filtering is v2-only)"}` — the clause after the colon names the actual cause | `1` |
| CLI `search --json` (`-c` named, or every collection) — `--changed-since <ref>` where the ref does not resolve in the collection's repository | `{"error": "--changed-since '<ref>' is not a valid git ref in <repo>"}` | `1` |
| MCP `search` / `search_collection` — caught `IndexedError` | `{"error": "…", "type": "<concrete class name>"}` (for example, `StorageError`) | n/a |
| MCP `search` / `search_collection` — unexpected search/status exception | `{"error": "Internal error: …", "type": "MCPError"}` | n/a |
| MCP `search_collection` — present on disk, unreadable manifest or no indexers | `{"error": "Collection 'x' exists on disk but has no usable index: …", "type": "MCPError"}` | n/a |
| MCP `search_collection` — collection unknown on disk | `{"error": "Collection 'x' not found or has no indexers"}` — **no `type`** | n/a |

Three asymmetries are deliberate and must not surprise a harness:
