# Search result reference (`indexed.search/1`)

Successful machine searches share one shape: `indexed index search --json`
and the MCP tools `search` / `search_collection` use the same payload builder.
For CLI calls, check the exit code before parsing stdout: a non-zero exit may
contain a non-JSON Rich error panel. On exit 0, parse JSON and read `schema`;
MCP results have no process exit code, so read `schema` directly.

- `schema: "indexed.search/1"` → the success shape below.
- no `schema`, an `error` string instead → the request failed. A failed request
  never reads as "nothing matched".

## Example payload

Captured from a real run, not authored by hand: two files (`cache.py` and
`caching.md`) indexed into a `files` collection, then

```bash
indexed index search "how is the cache keyed and invalidated" -c docs-demo --json
```

```json
{
  "schema": "indexed.search/1",
  "query": "how is the cache keyed and invalidated",
  "counts": {
    "documents": 2,
    "hits": 8
  },
  "collections": [
    "docs-demo"
  ],
  "collection_errors": [],
  "documents": [
    {
      "collection": "docs-demo",
      "source_type": "localFiles",
      "id": "caching.md",
      "url": "file:///var/lib/srv/hermes/profiles/prism/cache/scratch/docs-demo/caching.md",
      "score_kind": "l2_squared",
      "hits": [
        {
          "relevance": 0.5228,
          "score": 0.9544,
          "locator": {
            "kind": "headings",
            "headings": [
              "Caching notes",
              "Invalidation"
            ]
          },
          "text": "Caching notes > Invalidation\nEntries are dropped when the document's content hash changes. There is no time-based expiry."
        },
        {
          "relevance": 0.4585,
          "score": 1.083,
          "locator": {
            "kind": "headings",
            "headings": [
              "Caching notes"
            ]
          },
          "text": "Caching notes\nThe cache is keyed by collection and document id, so a document never reads another collection's entry."
        },
        {
          "relevance": 0.4143,
          "score": 1.1713,
          "locator": {
            "kind": "document"
          },
          "text": "caching.md"
        }
      ]
    },
    {
      "collection": "docs-demo",
      "source_type": "localFiles",
      "id": "cache.py",
      "path": "/var/lib/srv/hermes/profiles/prism/cache/scratch/docs-demo/cache.py",
      "score_kind": "l2_squared",
      "hits": [
        {
          "relevance": 0.462,
          "score": 1.0761,
          "locator": {
            "kind": "document"
          },
          "text": "cache.py"
        },
        {
          "relevance": 0.4125,
          "score": 1.1751,
          "locator": {
            "kind": "line_span",
            "start_line": 4,
            "end_line": 6
          },
          "text": "def cache_key(collection, document_id):\n    \"\"\"Stable cache key for one document of a collection.\"\"\"\n    return f\"{collection}:{document_id}\""
        },
        {
          "relevance": 0.4001,
          "score": 1.1998,
          "locator": {
            "kind": "line_span",
            "start_line": 14,
            "end_line": 16
          },
          "text": "def cache_put(store, collection, document_id, value):\n    store[cache_key(collection, document_id)] = value\n    return value"
        },
        {
          "relevance": 0.3968,
          "score": 1.2065,
          "locator": {
            "kind": "line_span",
            "start_line": 9,
            "end_line": 11
          },
          "text": "def cache_get(store, collection, document_id):\n    key = cache_key(collection, document_id)\n    return store.get(key)"
        },
        {
          "relevance": 0.3502,
          "score": 1.2997,
          "locator": {
            "kind": "line_span",
            "start_line": 1,
            "end_line": 3
          },
          "text": "\"\"\"Cache helpers for the demo collection.\"\"\""
        }
      ]
    }
  ]
}
```

Read that payload once and the rest of this page is a field list: document facts
(`collection`, `source_type`, `id`, `path`/`url`, `score_kind`) stated once per
document, hits carrying only `relevance`, `score`, `locator` and `text`.

## Top level

| Key | Type | Meaning |
|---|---|---|
| `schema` | string | Always `indexed.search/1` today. Branch on it; any incompatible change bumps it. |
| `query` | string | The query as submitted. |
| `counts.documents` | int | Number of entries in `documents`. |
| `counts.hits` | int | Total hits across all documents. |
| `collections` | string[] | Collections that were searched **successfully**. Empty means nothing was searched (no collections, or none searchable) — that is not the same as "searched and nothing matched". |
| `collection_errors` | object[] | Always present, `[]` when nothing failed. Each entry is `{"collection": "<name>", "error": "<message>"}`. A collection that reached the engine and failed appears here and is absent from `collections`. CLI collections with readable status but no indexers also appear here when other collections are searched. The CLI omits unreadable manifests from both arrays. MCP `search` enumerates by manifest presence and reports those failures here; `search_collection` checks status first and returns a top-level error for a present but unusable named collection (see Failures). |
| `documents` | object[] | Matched documents, best first. A document's position reflects its **best** hit; full-precision ties keep discovery order. Ranking happens before output scores are rounded. |
| `freshness` | object[], optional | Per-collection index-freshness verdicts, present only when the caller asked for them (`include_freshness` on the MCP tools, `--freshness` on the CLI). Each entry is `{"collection", "status": "fresh"\|"stale"\|"unknown", "reason", "baseline", "head", "filesChanged", "commitsBehind", "detachedHead", "summary"}`. A count git could not establish is `null`, never a plausible zero; `summary` is the one line every surface prints verbatim. See `.spec/tech-core.md` § Index Freshness. |

## Document object

| Key | Type | Meaning |
|---|---|---|
| `collection` | string | Which collection the document came from. |
| `source_type` | string, optional | The collection's reader type: `localFiles`, `jira`/`jiraCloud`, `confluence`/`confluenceCloud`, `outline` or `github`. A collection is fed by one reader, so this is stated once. Omitted when the collection's manifest does not record it. |
| `id` | string | The document's identity inside its collection (a file name, a page id). |
| `path` | string, optional | Absolute source path. Present when the hit locators supply exactly one distinct path; that path is hoisted here and removed from the locators. With multiple distinct paths, document `path` is omitted and each located hit retains its own `locator.path`. |
| `url` | string, optional | Where a human or agent opens the whole document. Omitted when unknown, and dropped when it only restates `path` as `file://<path>`. |
| `score_kind` | string | What `score` means for this document: `l2_squared` (v1 collections), `cosine` or `rerank` (v2 collections). |
| `hits` | object[] | The matched chunks of this document, best relevance first. |

## Hit object

| Key | Type | Meaning |
|---|---|---|
| `relevance` | float | Higher is better, **comparable across collections and engines**. Derived from the raw score per `score_kind`: `1 - score/2` for `l2_squared`, the score itself for `cosine`, a sigmoid of the logit for `rerank`. Normally 0–1, but it is not clamped: an `l2_squared` hit at a distance above 2 goes negative. Emitted values are rounded to 4 decimals after ranking; preserve payload order for near ties. Use relevance to compare hits across collections. |
| `score` | float | The raw engine score, rounded to 4 decimals. Only comparable **within one `score_kind`**. |
| `locator` | object | Where the hit sits. See below. |
| `text` | string | The matched chunk's text. Only an exact leading `# <metadata.file_path>\n` prefix is removed when that metadata path is present; other text stays unchanged. `kind: "document"` means position unknown: the text may still be a body fragment, not a title or whole-document chunk. |

## Locator kinds

`locator.kind` is load-bearing: read only the keys that kind declares. Precision
order is `line_span` > `page` > `headings` > `document`; a chunk that has line
data *and* headings gets `line_span` — provided a path is resolvable too (from the
chunk's `file_path` or its `file://` url), otherwise it falls through to `page`,
`headings` or `document`. A range is never invented to fill the field
— a source with no position known gets `document`.

| `kind` | Keys | What it means |
|---|---|---|
| `line_span` | `start_line`, `end_line`, optional `path` | Code, from tree-sitter chunks. Lines are **1-based and inclusive** — what `grep -n` prints and what your editor shows. `path` stays on each located hit when multiple distinct paths prevent a document `path`. |
| `page` | `page`, optional `path` | Positive page metadata, when supplied by the producer. `page` is 1-based; a PDF/DOCX source alone does not guarantee this metadata. |
| `headings` | `headings` | Prose: Markdown, Jira, Confluence, Outline. The heading path down to the chunk, e.g. `["Caching notes", "Invalidation"]`. Never empty — a chunk with no real headings degrades to `document` rather than claiming a precision it does not have. |
| `document` | *(none)* | The chunk carries no usable position. Open the source for context; the chunk can be any body fragment, including one of many chunks. |

## Failures

Check CLI exit status **before** parsing stdout. A non-zero exit is a failed
request; stdout can contain a JSON error body or a non-JSON Rich error panel.
For example, a missing named collection returns JSON and exits 1:

```console
$ indexed index search "x" -c nope --json
{
  "error": "Collection 'nope' not found"
}
$ echo $?
1
```

An `IndexedError` escaping the command reaches the top-level CLI handler, which
prints its Rich panel to **stdout** and exits 1, 2 for configuration errors, or
3 for storage errors. Ordinary logs and search notices go to stderr. The JSON
stdout guarantee applies to normal command returns, not this escape path.

Exit 0 alone does not mean success. An empty CLI store returns
`{"error": "No collections found"}` with exit 0. After the exit check, parse the
JSON and branch on `schema`; an error body has no success schema. In a success
payload, inspect `collection_errors` for partial failures and `collections` to
see what was searched. Empty `documents` with non-empty `collections` means
nothing matched in those collections. Empty `collections` means no collection was
searched successfully; inspect `collection_errors` to distinguish an empty store
from all searches failing.

MCP has no exit code. Read `schema` first. Global `search` reports per-collection
failures in `collection_errors`, including unreadable manifests. Named
`search_collection` resolves status first: a collection present on disk with an
unreadable manifest or no indexers returns a top-level `{"error": "…", "type":
"MCPError"}`; an unknown name returns `{"error": "Collection 'x' not found or has
no indexers"}` without `type`. Neither body has a success schema. If a boundary
catches an `IndexedError`, `type` preserves its concrete class name, such as
`StorageError`; unexpected search/status exceptions are wrapped as `MCPError`.

`--json` ignores `--compact` / `--no-content`; those shape the human view only.
CLI JSON and both MCP search tools always request matched chunk content, even
when MCP search config sets `include_matched_chunks = false`. The canonical
payload retains matched text and provenance.

The full failure table is in
[`.spec/tech-app.md` § Search result contract](../../.spec/tech-app.md#search-result-contract-indexedsearch1).
