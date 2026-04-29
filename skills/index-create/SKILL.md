---
name: index-create
description: Create a new semantic search index (collection) from local files, Jira, or Confluence using the indexed CLI. Use when setting up a searchable collection for a codebase or document source before searching with mcp__indexed__search.
argument-hint: [collection-name] [source-type]
allowed-tools: Bash, Read, Glob
---

Create a new indexed collection for semantic search.

## Existing Collections

!`indexed index inspect 2>/dev/null || echo "No collections yet."`

## Available Source Types

- **files** — Local files and directories (most common for codebases)
- **jira** — Jira issues (requires credentials in `.env`)
- **confluence** — Confluence pages (requires credentials in `.env`)

## Commands

### From local files
```bash
indexed index create files -c <collection-name> -p <path>
```

Common options:
- `-c, --collection` — Collection name (required)
- `-p, --path` — Root directory or file path
- `--include <regex>` — Regex patterns to include (repeatable)
- `--exclude <regex>` — Regex patterns to exclude (repeatable)
- `--force` — Overwrite existing collection with same name
- `--use-cache/--no-cache` — Enable/disable caching (default: enabled)
- `--fail-fast/--no-fail-fast` — Stop on first read error

Example for a Python codebase:
```bash
indexed index create files -c my-code -p ./src \
  --include '\.py$' \
  --exclude '__pycache__|\.pyc$'
```

### From Jira
```bash
indexed index create jira -c <collection-name>
```

### From Confluence
```bash
indexed index create confluence -c <collection-name>
```

## After Creation

Verify the collection was created:
```bash
indexed index inspect <collection-name>
```

Then use `/index-use` or `mcp__indexed__search` to query it.
