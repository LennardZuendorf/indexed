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

## Migrating a v1 Collection to the v2 Engine

Collections created before the v2 engine run on v1 (FAISS). Convert one to v2 on
explicit request with `migrate` — it is safe by design (build-aside, validate,
backup, rollback) and never touches the v1 data until the new collection is
durably written and validated:

```bash
indexed index migrate <collection> --dry-run   # preview: doc/chunk counts + target model/store, changes nothing
indexed index migrate <collection>             # migrate offline; keeps <collection>.v1-backup
indexed index migrate <collection> --purge-backup   # migrate (or clean up) and remove the backup
```

- **Offline by default**: re-embeds from the collection's stored content — no
  source access or credentials needed, no network. Use `--from-source` to
  re-read the live source instead.
- **Backup + rollback**: the original v1 collection is preserved as
  `<collection>.v1-backup` until you run `--purge-backup`. A failed migration
  leaves v1 fully intact (no partial v2 collection). If the final swap fails the
  original is restored byte-identical.
- **Validation**: before swapping, migration checks the document/chunk counts and
  runs a probe search against the new v2 collection.

Verify afterward with `indexed index inspect <collection>` (it should report
engine `2` with the embedding model and `simple` vector store) and a search.
