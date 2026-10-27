# Search result reference (`indexed.search/1`)

Every machine consumer of indexed gets one shape: `indexed index search --json`
and the MCP tools `search` / `search_collection` return the same object, built by
the same code. Read `schema` first and branch on it — never on whether a
particular key happens to be present.

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
| `collection_errors` | object[] | Always present, `[]` when nothing failed. Each entry is `{"collection": "<name>", "error": "<message>"}`. A collection that failed appears here and is absent from `collections`; it never turns into a silent zero. |
| `documents` | object[] | Matched documents, best first. A document's position reflects its **best** hit; ties keep discovery order. |

## Document object

| Key | Type | Meaning |
|---|---|---|
| `collection` | string | Which collection the document came from. |
| `source_type` | string, optional | The collection's reader type: `localFiles`, `jira`/`jiraCloud`, `confluence`/`confluenceCloud`, `outline` or `github`. A collection is fed by one reader, so this is stated once. Omitted when the collection's manifest does not record it. |
| `id` | string | The document's identity inside its collection (a file name, a page id). |
| `path` | string, optional | Absolute source path. Present when the document's hits agree on one file — the path is then hoisted here and removed from each hit's locator. A hit whose file genuinely differs keeps its own `locator.path`. |
| `url` | string, optional | Where a human or agent opens the whole document. Omitted when unknown, and dropped when it only restates `path` as `file://<path>`. |
| `score_kind` | string | What `score` means for this document: `l2_squared` (v1 collections), `cosine` or `rerank` (v2 collections). |
| `hits` | object[] | The matched chunks of this document, best relevance first. |

## Hit object

| Key | Type | Meaning |
|---|---|---|
| `relevance` | float | 0–1, higher is better, **comparable across collections and engines**. Derived from the raw score per `score_kind`: `1 - score/2` for `l2_squared`, the score itself for `cosine`, a sigmoid of the logit for `rerank`. Use this to rank hits from different collections against each other. |
| `score` | float | The raw engine score, rounded to 4 decimals. Only comparable **within one `score_kind`**. |
| `locator` | object | Where the hit sits. See below. |
| `text` | string | The matched chunk's text as indexed, with the `# <path>` context prefix that code chunks carry removed (the path is already in the locator). For `kind: "document"` this is the whole-document chunk — typically just the title or file name. |

## Locator kinds

`locator.kind` is load-bearing: read only the keys that kind declares. Precision
order is `line_span` > `page` > `headings` > `document`; a chunk that has line
data *and* headings gets `line_span` — provided a path is resolvable too (from the
chunk's `file_path` or its `file://` url), otherwise it falls through to `page`,
`headings` or `document`. A range is never invented to fill the field
— a source with no position known gets `document`.

| `kind` | Keys | What it means |
|---|---|---|
| `line_span` | `start_line`, `end_line`, optional `path` | Code, from tree-sitter chunks. Lines are **1-based and inclusive** — what `grep -n` prints and what your editor shows. `path` appears only when it differs from the document's `path`. |
| `page` | `page`, optional `path` | Paginated documents (PDF, DOCX) parsed by Docling. `page` is 1-based. |
| `headings` | `headings` | Prose: Markdown, Jira, Confluence, Outline. The heading path down to the chunk, e.g. `["Caching notes", "Invalidation"]`. Never empty — a chunk with no real headings degrades to `document` rather than claiming a precision it does not have. |
| `document` | *(none)* | The source carries no position (a one-chunk document, a connector record without anchors). Hit the document, nothing narrower. |

## Failures

A failed request returns an `error` envelope with no `schema` key, for example:

```console
$ indexed index search "x" -c nope --json
{
  "error": "Collection 'nope' not found"
}
$ echo $?
1
```

On the CLI, `--json` writes the payload to stdout and nothing else — log lines and
notices (a skipped unsearchable collection, a no-op `--rerank`) go to stderr, and a
non-zero exit means there is no payload to trust. Over MCP there is no exit code:
branch on `schema` first, then on `collections` being empty.

`--json` ignores `--compact` / `--no-content`; those shape the human view only. The
machine payload is fixed.

Requesting counts without matched chunks (`include_matched_chunks = false` in MCP
search config) degrades to `documents: []` and `counts.hits: 0` while `collections`
still lists what was searched — the provenance lives in the chunks, so there is
nothing to locate without them.

The full failure surface (every envelope, exit code and the one MCP body that
carries no `type`) is pinned in
[`.spec/tech-app.md` § Search result contract](../../.spec/tech-app.md#search-result-contract-indexedsearch1).
