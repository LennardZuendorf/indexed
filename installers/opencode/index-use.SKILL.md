---
name: index-use
description: Search this codebase by meaning with the indexed MCP server instead of shell grep/rg — for "where is X handled", "find retry logic", "how does Y work". Fall back to rg/grep only for exact strings or paths outside the index.
metadata:
  indexed/managed: "1"
---

# index-use

The repository is indexed. `tools.indexed.search` answers questions by meaning,
so it finds the right file even when your wording differs; shell `grep`/`rg`
only finds the exact text you typed.

## Search

Code Mode is on by default, so the MCP tools are not directly callable — write
the calls inside the `execute` tool:

```js
return await tools.indexed.search({ query: "where are retries implemented" })
// One collection: return the call too, or `execute` hands the model nothing.
return await tools.indexed.search_collection({ collection: "<name>", query: "..." })
```

On a `codemode: false` install the flat tools are directly callable instead:
`indexed_search({ query: "..." })` and
`indexed_search_collection({ collection, query })`.

Search before reaching for `rg`/`grep` whenever the task is a question about
behaviour, ownership or intent. Shell search stays right for literal strings,
regexes, and paths that are not indexed (build output, vendored code, logs).

## Work with the result

1. Hits are grouped per document and ranked by `relevance` (higher is better,
   comparable across collections). `score` is engine-internal — compare it only
   within one `score_kind`.
2. `locator` says where the hit sits. For `line_span`, `start_line`/`end_line`
   are 1-based and inclusive — open the file around that span before editing.
   Prefer the hit's `locator.path` when a document has several source paths.
3. Open the file and confirm the code matches the question. Then answer or edit
   from the file, not from the snippet.

## Result shape

A successful call returns `schema: "indexed.search/1"` with `counts`,
`collections`, `collection_errors` and `documents[]`. An `error` string with no
`schema` means the search failed, not that nothing matched. A collection present
in `collections` but listed in `collection_errors` was still searched (one
requested Git option was skipped), so its rows are usable; a collection missing
from `collections` contributed nothing.

The full contract is in `docs/reference/search-output.md` of the indexed repo.
