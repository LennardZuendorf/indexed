---
name: index-use
description: Search the codebase using semantic search via the indexed MCP server. ALWAYS prefer this over Grep/Glob when looking for code by meaning, intent, or concept (e.g. "where is authentication handled", "find retry logic"). Only fall back to Grep for exact literal patterns.
argument-hint: [search-query]
allowed-tools: mcp__indexed__search, mcp__indexed__search_collection, Bash, Read, Grep, Glob, WebFetch
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

Successful calls return the documented payload (`schema: "indexed.search/1"`) —
the same object `indexed index search --json` prints. For CLI calls, check the
exit code before parsing stdout; escaping errors can print a non-JSON Rich panel.
Exit 0 can still contain an error body. Both MCP tools always request matched
content, including when search config disables it. Documents are grouped and ranked by
their best hit:

- `schema` — `indexed.search/1`. Branch on it; an `error` string with no `schema`
  means the search failed, not that nothing matched
- `counts` — `{documents, hits}`; `collections` — what was searched;
  `collection_errors` — collections that failed (always present, `[]` when none)
- `documents[]` — each states `collection`, optional `source_type`, `id`, optional `path` /
  `url` and `score_kind` once
- `documents[].hits[]` — `relevance` (higher is better, comparable across
  collections; normally 0–1 but not clamped, so `l2_squared` can go negative),
  `score` (raw engine number, only comparable within one `score_kind`),
  `locator`, `text`
- `locator` — where the hit sits; read only the keys its `kind` declares:
  `line_span` (`start_line`/`end_line`, 1-based inclusive — what `grep -n` prints),
  `page` (1-based, only when page metadata is supplied), `headings` (heading path),
  or `document` (position unknown, including body fragments)

Global `search` reports individual collection failures in `collection_errors`.
Named `search_collection` can instead return a top-level `error` without `schema`:
a present but unusable collection includes `type: "MCPError"`; an unknown name
has no `type`. Caught `IndexedError` types preserve their concrete class name.

## Workflow

1. Call `mcp__indexed__search(query="...")` with a natural-language query
2. Review the hits — `relevance` sorts them, `locator` says where to look
3. For local sources, prefer the hit's `locator.path`, then document `path`.
   Multiple source paths omit document `path` and retain each hit's `locator.path`.
   If only a local `file://` URL is available, parse the URL and percent-decode its
   path before `Read` (for example, `file:///tmp/my%20notes.md` becomes
   `/tmp/my notes.md`; an empty or `localhost` authority identifies a local file).
   Use the inclusive `start_line` / `end_line` span to read surrounding context.
   For HTTP/HTTPS URLs, use `WebFetch` or an available source connector instead of
   filesystem `Read`; authenticated sources need their authorized connector.
4. Only fall back to Grep/Glob if MCP search doesn't cover your use case
