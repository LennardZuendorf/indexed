---
type: feature-plan
feature: branch-aware-collections
sibling: tech.md
parent: ../../plan.md
updated: 2026-06-23
---

# Feature: Branch-Aware Collections — Implementation Plan

Five testable units take the collection from a single silent index to per-branch
variants with cross-branch embedding reuse, branch resolution with a non-git
fallback, and lazy migration of legacy collections. Each unit is test-first and
lands behind the existing storage/persistence seams.

**Parent:** [../../plan.md](../../plan.md) / **Requirements:** [product.md](product.md) / **Architecture:** [tech.md](tech.md)

**Feature gate:** independent foundation — can start now; natural companion to the
upcoming filewatcher PR but does not depend on it.

## Problem Frame

A collection's one FAISS index reflects whatever branch was checked out at index
time, so branch switches silently return stale results. We add a branch segment
to the storage layout, a shared content-hash embedding store so unchanged chunks
are embedded once, git-based active-branch selection with a `default` fallback,
and transparent migration of existing collections.

## Requirements Trace

| Requirement | Units |
|-------------|-------|
| R1 — per-branch index variants | branch-aware-collections/2, branch-aware-collections/4 |
| R2 — embedding reuse via content_hash | branch-aware-collections/3, branch-aware-collections/4 |
| R3 — branch resolution + selection + non-git fallback | branch-aware-collections/1, branch-aware-collections/4, branch-aware-collections/5 |
| R4 — backward-compat migration | branch-aware-collections/2, branch-aware-collections/5 |

## Key Technical Decisions

- Reuse the git plumbing already in `change_tracker.py`; add only
  `--abbrev-ref HEAD`. No new git dependency.
- Dedup on the existing `ParsedChunk.content_hash` — no schema change to chunks.
- Branch segment is a sanitized path component (`feature/x` → `feature__x`);
  non-git and detached HEAD both collapse to `default`, preserving today's
  behavior bit-for-bit for non-git sources.
- Migration is lazy and atomic (DiskPersister rename), never a forced re-embed.

### branch-aware-collections/1 — Branch resolution + state

**Goal:** Resolve the active branch from git with a robust fallback and record it
in indexing state.
**Requirements:** R3
**Dependencies:** —
**Files:**
```
packages/indexed-core/src/core/v1/engine/core/branch_resolver.py   [NEW]
packages/indexed-connectors/src/connectors/files/change_tracker.py  ~ add
  last_indexed_branch + _current_git_branch()
tests/unit/indexed_core/test_branch_resolver.py                     [NEW]
```
**Test scenarios:**
- git repo on a named branch resolves to that branch
- detached HEAD (`HEAD`) resolves to `default`
- non-git directory resolves to `default` (no exception)
- `sanitize("feature/x")` → `feature__x`
- `build_state()` populates `last_indexed_branch`
**Verification:** `uv run pytest tests/unit/indexed_core/test_branch_resolver.py -q`

### branch-aware-collections/2 — Branch-aware storage layout

**Goal:** Add branch-scoped path helpers and the new layout in `storage.py`.
**Requirements:** R1, R4
**Dependencies:** branch-aware-collections/1
**Files:**
```
packages/indexed-config/src/indexed_config/storage.py  ~ get_branch_root(),
  get_embeddings_store_path(), sanitize_branch(); docstring
tests/unit/indexed_config/test_branch_storage.py        [NEW]
```
**Test scenarios:**
- `get_branch_root(root, "docs", "main")` ends with `collections/docs/branches/main`
- `get_embeddings_store_path` points at `collections/docs/embeddings`
- helpers respect both global and local roots
**Verification:** `uv run pytest tests/unit/indexed_config/test_branch_storage.py -q`

### branch-aware-collections/3 — Content-hash embedding store

**Goal:** Persist and reuse embeddings keyed on `content_hash`.
**Requirements:** R2
**Dependencies:** branch-aware-collections/2
**Files:**
```
packages/indexed-core/src/core/v1/engine/core/embedding_store.py  [NEW]
tests/unit/indexed_core/test_embedding_store.py                   [NEW]
```
**Test scenarios:**
- first `get_or_embed` embeds all misses and persists `store.json`
- second call with overlapping hashes embeds only the new misses
- changed `content_hash` is treated as a miss and embedded
- store round-trips through `DiskPersister` (use `tmp_path`)
**Verification:** `uv run pytest tests/unit/indexed_core/test_embedding_store.py -q`

### branch-aware-collections/4 — Wire creator + searcher to branches

**Goal:** Route create/update writes and search reads through the active branch
variant, using the embedding store.
**Requirements:** R1, R2, R3
**Dependencies:** branch-aware-collections/1, branch-aware-collections/2, branch-aware-collections/3
**Files:**
```
packages/indexed-core/src/core/v1/engine/core/documents_collection_creator.py   ~
packages/indexed-core/src/core/v1/engine/core/documents_collection_searcher.py   ~
tests/unit/indexed_core/test_branch_aware_pipeline.py                            [NEW]
```
**Test scenarios:**
- indexing two branches writes two variants under `branches/`
- searching branch A excludes A-only-absent chunks unique to branch B
- a chunk shared across branches calls the embedder once (assert via spy)
- searcher selects the variant matching the resolved branch
**Verification:** `uv run pytest tests/unit/indexed_core/test_branch_aware_pipeline.py -q`

### branch-aware-collections/5 — Legacy migration

**Goal:** Migrate existing single-index collections to the default branch on
first access, with a schema-version stamp.
**Requirements:** R3, R4
**Dependencies:** branch-aware-collections/2, branch-aware-collections/4
**Files:**
```
packages/indexed-core/src/core/v1/engine/core/migration.py  [NEW]
packages/indexed-core/src/core/v1/engine/core/documents_collection_searcher.py  ~
  call migration on legacy read
tests/unit/indexed_core/test_legacy_migration.py            [NEW]
```
**Test scenarios:**
- a fixture legacy collection becomes searchable as `default` with no re-index
- migrated `manifest.json` records `schemaVersion`
- a non-git legacy collection keeps working unchanged after migration
- migration is idempotent (second run is a no-op)
**Verification:** `uv run pytest tests/unit/indexed_core/test_legacy_migration.py -q`
