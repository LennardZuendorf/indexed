---
name: index-use
description: Search the codebase with the indexed MCP server instead of shell grep/rg. Use it for "where is X handled", "find retry logic", "how does Y work" — anything describing behaviour rather than a literal string. Falls back to rg/grep only for exact patterns or paths that are not indexed.
---

# index-use

The repository is indexed. `mcp__indexed__search` and
`mcp__indexed__search_collection` answer questions by meaning, so they find the
right file even when the wording differs; shell `grep`/`rg` only find the exact
text you typed.

## Search

- All collections (preferred):
  `mcp__indexed__search(query="where are retries implemented")`
- One collection:
  `mcp__indexed__search_collection(collection="<name>", query="...")`

Call them before reaching for `rg`/`grep` whenever the task is a question about
behaviour, ownership, or intent. Use shell search for literal strings, regexes,
and files outside the index (build output, vendored code, logs).

## Work with the result

1. Hits are grouped per document and ranked by `relevance` (higher is better,
   comparable across collections). `score` is engine-internal — compare it only
   within one `score_kind`.
2. `locator` says where the hit sits. For `line_span`, `start_line`/`end_line`
   are 1-based and inclusive — read the file around that span before editing.
3. Open the file and confirm the code matches the question. Then answer or edit
   from the file, not from the snippet.

## Result shape

A successful call returns `schema: "indexed.search/1"` with `counts`,
`collections`, `collection_errors` and `documents[]`. An `error` string with no
`schema` means the search failed, not that nothing matched. A collection present
in `collections` but listed in `collection_errors` was still searched (one
requested Git option was skipped), so its rows are still usable; a collection
missing from `collections` contributed nothing.

The full contract is in `docs/reference/search-output.md` of the indexed repo.
