---
type: tech
updated: 2026-11-22
applies: "src/indexed/connectors/**"
---

# Files Traversal — Storage Root Is Never Source Content

A files collection must never index indexed's own storage. Both modes live in a
directory named `.indexed` — `./.indexed` (local) and `~/.indexed` (global) —
holding `config.toml`, `.env`, `data/collections/*` and caches. Two layers
enforce that in `connectors/files/`:

- **Name rule:** `.indexed` is in `DEFAULT_EXCLUDED_DIRS`
  (`schema.py`), pruned during traversal before descending, independent of
  `.gitignore` and `include_patterns`, and for nested workspaces too.
- **Path rule:** `FilesDocumentReader` guards the *resolved* storage roots
  (`default_storage_roots()` → `<base>/.indexed` and `~/.indexed`) and prunes
  any directory equal to or inside one, plus explicit `specific_files` passed by
  an incremental update. This holds even when `excluded_dirs` is overridden
  without `.indexed`.

Consequences, deliberate:

- A workspace's `.indexed/` is **reserved**; it cannot be re-enabled as source.
- A *nested* directory literally named `.indexed` is skipped by the name rule
  and can only be re-enabled by an explicit `excluded_dirs` list that omits it.
- Pointing `--path` *inside* a storage root is an explicit request: a root that
  contains the scan base is dropped from the guard, so such a scan still works.

Why it matters beyond tidiness: `.indexed/.gitignore` is untracked, so without
the guard `search --changed-since <ref>` reported the collection's own storage
file as changed (issue #279 follow-up). Collections created before the fix keep
the stale document until a re-create (`--force`) or the next `update`, which
drops it as a deletion via change tracking.
