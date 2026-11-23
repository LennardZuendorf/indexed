---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Persistence Strategy

`DiskPersister` atomic writes: write temp file → `fsync()` → rename (atomic on POSIX).
Prevents corruption from process/system crashes and disk-full errors.

**Durability invariants:**
- The FAISS index is persisted on **every** mutating path — create, add,
  remove-then-add, deletions-only, and explicit-deletions — so on-disk vectors
  never outlive their mapping keys (no orphaned ids / `KeyError` on later search).
- A failed `create` **builds aside and rename-swaps** into place, so an error
  mid-run never destroys the prior collection of the same name.
- A zero-chunk batch (e.g. an empty-body document) is a **no-op**, not a crash.

On-disk layout (dirs owned by `src/indexed/config/`): [Storage Directory Structure](../config/config-storage-directory-structure.md).
