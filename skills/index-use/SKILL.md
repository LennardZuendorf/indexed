---
name: index-use
description: Search the codebase using semantic search via the indexed MCP server. ALWAYS prefer this over Grep/Glob when looking for code by meaning, intent, or concept (e.g. "where is authentication handled", "find retry logic"). Only fall back to Grep for exact literal patterns.
argument-hint: [search-query]
allowed-tools: mcp__indexed__search, mcp__indexed__search_collection, Bash, Read
---

Use the indexed MCP server for semantic codebase search instead of Grep/Glob.

## Available Collections

!`indexed index inspect 2>/dev/null || echo "No collections indexed yet. Run /index-create first."`

## How to Search

### Search all collections (preferred)
Call the MCP tool directly:
```
mcp__indexed__search(query="$ARGUMENTS")
```

### Search a specific collection
```
mcp__indexed__search_collection(collection="<name>", query="$ARGUMENTS")
```

## When to Use MCP Search vs Grep/Glob

| Goal | Tool |
|------|------|
| "Where is X handled?" / concept search | **mcp__indexed__search** |
| Finding related implementations | **mcp__indexed__search** |
| Understanding code intent | **mcp__indexed__search** |
| Exact regex or literal string match | Grep |
| Finding files by name/glob pattern | Glob |

## Result Format

Both tools return the documented payload (`schema: "indexed.search/1"`) — the same
object `indexed index search --json` prints. Documents are grouped and ranked by
their best hit:

- `schema` — `indexed.search/1`. Branch on it; an `error` string with no `schema`
  means the search failed, not that nothing matched
- `counts` — `{documents, hits}`; `collections` — what was searched;
  `collection_errors` — collections that failed (always present, `[]` when none)
- `documents[]` — each states `collection`, `source_type`, `id`, optional `path` /
  `url` and `score_kind` once
- `documents[].hits[]` — `relevance` (0–1, higher is better, comparable across
  collections), `score` (raw engine number, only comparable within one `score_kind`),
  `locator`, `text`
- `locator` — where the hit sits; read only the keys its `kind` declares:
  `line_span` (`start_line`/`end_line`, 1-based inclusive — what `grep -n` prints),
  `page` (1-based), `headings` (heading path), or `document` (position unknown)

## Workflow

1. Call `mcp__indexed__search(query="...")` with a natural-language query
2. Review the hits — `relevance` sorts them, `locator` says where to look
3. Use `Read` on the hit's document (`path` or `url`, then `locator` lines) for the
   full context around the match
4. Only fall back to Grep/Glob if MCP search doesn't cover your use case
