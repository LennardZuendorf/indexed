---
type: feature-product
feature: collection-registry
sibling: tech.md
parent: ../../product.md
updated: 2026-11-22
---

# Feature: Shared Collection Registry — Product

**Parent:** issue [#346](https://github.com/LennardZuendorf/indexed/issues/346) ·
milestone [#229](https://github.com/LennardZuendorf/indexed/issues/229).

## Problem

A collection's identity is its directory name under one storage root. Two
projects that want the same index therefore keep two copies of it: two FAISS
indexes, two embed passes, two things to update. Copying is not even obvious —
it is what happens by default because the project-local store is the only place
a collection can live.

## Outcome

A collection that lives in the global store has a **stable id** and a
**documented migration**: a project can point at it instead of owning a copy,
and can undo that choice. This is the spine #344 (a committed repository
definition naming collections) and #345 (per-request scope) build on; neither is
in this feature.

## Requirements

- **R1 — Reuse is real reuse.** Two project directories can use one collection
  that exists once on disk. A second copy is a failure, not an optimisation.
- **R2 — The migration is inspectable and safe to interrupt.** `--dry-run`
  reports every collection, its target, its size in bytes and any collision,
  and changes nothing. Re-running a dry run yields the same report. An
  interrupted migration resumes; a completed one re-run changes nothing.
- **R3 — Rollback is a first-class path.** `--rollback` restores the project's
  original local collection and the restored store still answers queries under
  the engine that built it.
- **R4 — Collisions are named, never resolved silently.** A name already in the
  shared store stops the migration unless the user chooses `adopt` (an
  identical copy) or `rename`.
- **R5 — The pointer decides where commands read.** CLI and MCP resolve the
  collections root through the same function, so a pointed workspace searches
  the shared store in both surfaces.
- **R6 — Verification strength is the user's choice, and the default is stated.**
  `--verify structural` (default, in `--help` and the README) compares manifest
  and file names/sizes, not content; `--verify hash` streams a SHA-256 of every
  file, refuses mismatches by naming the files, and `adopt` never deletes a
  local copy whose content differs.

## Non-goals

- Per-request scope resolution (#345) and committed repository definitions
  (#344).
- Removing the local/global storage modes (milestone #229's end state).
- A lock across concurrent migrations; two workspaces migrating at the same
  moment are independent (per-workspace journals), and registry writes are
  atomic but last-writer-wins.
- Multi-user or server-side sharing: the global store is still one user's
  `~/.indexed`.

## Acceptance (from the issue)

| Requirement | Test |
|---|---|
| R1 | `tests/system/test_collection_registry.py::test_two_workspaces_reuse_one_collection` |
| R2 | `tests/system/test_collection_registry.py::test_dry_run_is_idempotent_and_resumable` |
| R3 | `tests/system/test_collection_registry.py::test_rollback_restores_local_collection_and_engine_reads_correct_engine` |
| R4 | `tests/unit/indexed/storage/test_migration.py` (plan/adopt/rename/refuse) |
| R5 | the R1 test searches from both workspaces through the CLI |
| R6 | `tests/unit/indexed/storage/test_migration.py::test_hash_verify_refuses_same_size_collections_and_names_the_file`, `::test_adopt_with_hash_never_deletes_a_mismatching_local_copy`, `::test_hash_verify_peak_memory_stays_bounded_on_a_large_file` |
