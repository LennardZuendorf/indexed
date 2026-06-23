---
type: feature-product
feature: branch-aware-collections
sibling: tech.md
parent: ../../product.md
updated: 2026-06-23
---

# Feature: Branch-Aware Collections — Product

Today a collection holds a single FAISS index that silently reflects whichever
git branch was checked out at index time. Switching branches yields stale or
wrong search results with no warning. This feature stores per-branch index
variants and makes branch switches near-instant by reusing embeddings for chunks
that are identical across branches (keyed on each chunk's existing
`content_hash`). When the source is not a git repository, behavior is unchanged.

**Parent:** [../../product.md](../../product.md) / **Architecture:** [tech.md](tech.md) / **Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | Per-branch index storage layout; the content-hash-keyed embedding-reuse store; branch resolution (`git rev-parse --abbrev-ref HEAD`) and active-branch selection at search/update; non-git fallback; backward-compatible migration of existing single-index collections. |
| **Does not own** | The filewatcher (separate upcoming PR — it just triggers re-index); git metadata fields on chunks (the *git-metadata-enrichment* feature); commit/history documents (the *git-history-documents* feature); the embedding model and FAISS indexer internals. |

---

## Requirements

### Requirement: Per-branch index variants SHALL be stored independently

A collection indexed against a git source MUST persist a separate index variant
per branch so that searching one branch never returns chunks unique to another.

#### Scenario: Two branches, isolated results
- **Given** a collection indexed on branch `main` and later on branch `feature-x`
- **When** the user searches while `feature-x` is checked out
- **Then** results MUST come from the `feature-x` variant and MUST NOT include
  chunks that exist only on `main`

### Requirement: Embeddings SHALL be reused across branches via content_hash

Chunks whose `content_hash` is unchanged across branches MUST NOT be re-embedded;
the embedding MUST be reused from a shared, content-hash-keyed store.

#### Scenario: Identical chunk embedded once
- **Given** a chunk with `content_hash` `H` present on both `main` and `feature-x`
- **When** `feature-x` is indexed after `main`
- **Then** the chunk MUST reuse the cached embedding for `H` and the embedder
  MUST NOT be invoked for that chunk

#### Scenario: Changed chunk is re-embedded
- **Given** a chunk edited on `feature-x` so its `content_hash` differs from `main`
- **When** `feature-x` is indexed
- **Then** the changed chunk MUST be embedded fresh and stored under its new hash

### Requirement: Active branch SHALL be resolved from git with a non-git fallback

The active branch MUST be resolved via `git rev-parse --abbrev-ref HEAD` and used
to select the variant on search and update; sources that are not git repositories
MUST fall back to a single default variant (today's behavior).

#### Scenario: Branch selected on search
- **Given** the working tree is on branch `release-2`
- **When** the user runs a search against a branch-aware collection
- **Then** the `release-2` variant MUST be selected

#### Scenario: Non-git source uses default variant
- **Given** a source directory that is not inside a git repository
- **When** the collection is created and searched
- **Then** a single default variant MUST be used and no branch resolution error
  is raised

### Requirement: Existing single-index collections SHALL migrate transparently

Legacy collections created before this feature MUST keep working; on first access
they MUST be treated as the default branch via a schema-version bump, with no data
loss and no forced re-index.

#### Scenario: Legacy collection still searchable
- **Given** a collection created under the old single-index layout
- **When** it is opened after this feature ships
- **Then** it MUST be readable as the default-branch variant without re-indexing

#### Scenario: Schema version recorded
- **Given** a legacy collection is migrated to the branch-aware layout
- **When** its manifest is read
- **Then** the manifest MUST record the new `schemaVersion`

---

## Non-Goals

- Cross-branch diff/merge of search results.
- Automatic re-index on branch switch (the filewatcher PR owns triggering).
- Per-commit or historical indexing (owned by *git-history-documents*).

## Open Questions

- Eviction policy for stale branch variants (deleted branches) — defer to a
  follow-up `indexed branch prune` command.
