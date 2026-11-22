---
type: feature-tech
feature: collection-registry
sibling: product.md
parent: ../../tech.md
updated: 2026-11-22
---

# Feature: Shared Collection Registry — Tech

## Modules

| Path | Role |
|---|---|
| `src/indexed/config/collections_registry.py` | Registry + pointer files and their atomic writes. Leaf layer: no `core` import. |
| `src/indexed/cli/storage/commands/_migration.py` | Plan / migrate / rollback, the per-workspace journal, fingerprints. |
| `src/indexed/cli/storage/commands/migrate.py` | Thin Typer command; renders `MigrationReport`. |
| `src/indexed/cli/storage/cli.py` | `indexed storage` group assembly. |
| `src/indexed/cli/composition.py` | `resolve_collections_context` honours the workspace pointer. |
| `src/indexed/cli/_app_setup.py` | Registers `storage` + `storage migrate` (flat and grouped). |

## On-disk contract

```
~/.indexed/data/registry.json                 # registry (stable ids)
{"version": "1", "collections": [
   {"id": "<32 hex>", "name": "docs", "engine": "1"|"2",
    "path": "collections/docs", "workspace": "/abs/project",
    "registered_at": "<iso8601Z>", "fingerprint": "<sha256>",
    "linked_workspaces": ["/abs/project", "/abs/other"]}
]}

~/.indexed/data/registry-migration-<sha8>.json  # journal, one per workspace
{"version": "1", "workspace": "/abs/project", "started_at": ..., "completed_at": ...,
 "steps": [{"name", "engine", "source", "target", "action": "move"|"adopt",
            "fingerprint", "id", "state": "planned|moved|registered|linked|rolled_back"}]}

<project>/.indexed/collections.json            # pointer
{"version": "1", "collections_root": "/abs/.indexed/data/collections",
 "collections": {"docs": "<32 hex>"}}
```

`registry-migration-<sha8>.json` sits under `data/`, not under
`data/collections/`, so no discovery site has to learn a new exclusion. Ids are
`uuid4().hex`, minted once at registration and never re-derived from the name.

## Why this shape

- **A stable id is a lookup key, not a rename.** Directory name stays the
  collection name everywhere in the engine (only one `collections_path` reaches
  the facade), so the registry records the mapping id → name/path; nothing in
  `core` learns about ids yet. #344/#345 can add per-name resolution on top.
- **Reuse is explicit because the filesystem says no.** `DiskPersister._safe_join`
  realpath-refuses writes that escape the base directory and v1 discovery walks
  with `followlinks=False`, so a symlinked collection is both unwritable and
  invisible. The pointer file (read by `resolve_collections_context`, shared by
  CLI and MCP) is the honest mechanism.
- **The journal is per workspace and reconciled from disk.** A step writes its
  state AFTER the data move; a crash in between leaves `planned` with the data
  already at the target. Resume therefore compares the filesystem to the
  recorded fingerprint instead of trusting the state, and a partial cross-device
  copy (target without `manifest.json`) is discarded and retried from the intact
  source.
- **Adopt deletes; it never duplicates.** `--on-collision adopt` is only
  offered when the structural fingerprints match (manifest bytes + sorted file
  list with sizes — cheap on a multi-GB index, and enough to answer "same
  collection?"). Rollback of an adopt step re-materialises the local copy from
  the shared one, which is byte-identical by construction, and leaves the shared
  collection (and its other workspace links) untouched.
- **Dry run is read-only by construction.** `plan()` never writes; the CLI's
  dry-run path returns before the journal is created.

## Failure surfaces

- Registry/payload with an unknown `version`, unparseable JSON, duplicate ids,
  or a missing identity key → `CollectionRegistryError` (a `StorageError`),
  never an empty registry: silently forgetting ids is how a second copy gets
  created.
- Same name at a different path in `add()` → refused, so a resumed run cannot
  re-point an id at different bytes.
- `_describe_local` goes through `engine_descriptors`, so an unclassifiable
  collection (corrupt/unknown manifest) stops the migration instead of being
  left behind while the workspace is re-pointed.
- A pointer whose `collections_root` has disappeared is ignored (fall back to
  the workspace's own storage) rather than failing every command.

## Evidence

`tests/system/test_collection_registry.py` (three acceptance tests, real
collections, real embeddings) and
`tests/unit/indexed/{config/test_collections_registry,storage/test_migration}.py`.
Each acceptance test was shown red under a targeted mutation (ignore an existing
shared copy / skip resume reconciliation / skip the rollback move).
