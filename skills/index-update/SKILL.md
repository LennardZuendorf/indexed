---
name: index-update
description: Update or refresh an existing search collection when source files have changed. Re-reads documents from their original source, re-chunks changed content, and rebuilds the FAISS vector index.
argument-hint: [collection-name]
allowed-tools: Bash, Read
---

Refresh an existing indexed collection to reflect source changes.

## Current Collections

!`indexed index inspect 2>/dev/null || echo "No collections found. Run /index-create first."`

## Update Command

```bash
indexed index update $ARGUMENTS
```

This will:
1. Re-read documents from the collection's original source (files / Jira / Confluence)
2. Re-chunk any changed content
3. Re-embed changed chunks via the configured embedding model
4. Rebuild the FAISS vector index
5. Persist the updated index to disk

## Verify

After updating, inspect the collection to confirm the new document/chunk counts:
```bash
indexed index inspect $ARGUMENTS
```

## When to Update

- Source files have been modified since the collection was created
- You want the index to reflect current code state
- After significant refactors or new feature additions

## When to Recreate Instead

If the source configuration itself has changed (different path, include/exclude patterns, etc.), recreate with `/index-create` and `--force` rather than updating.
