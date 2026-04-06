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

Results are ranked by relevance (lowest L2 distance = best match). Each result contains:

- `rank` — position in result list
- `relevance_score` — similarity score
- `collection` — source collection
- `document_id` / `document_url` — source reference
- `chunk_number` — matched chunk position
- `text` — the actual matched content

## Workflow

1. Call `mcp__indexed__search(query="...")` with a natural-language query
2. Review ranked results — best matches first
3. Use `Read` to open the source files for the top hits
4. Only fall back to Grep/Glob if MCP search doesn't cover your use case
