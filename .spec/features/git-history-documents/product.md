---
type: feature-product
feature: git-history-documents
sibling: tech.md
parent: ../../product.md
updated: 2026-06-23
---

# Feature: Git History Documents — Product

Code answers *what* and *how* but not *why*. This feature makes a repository's
commit history semantically searchable — "find the commit that introduced retry
logic", "why was the FAISS index type chosen" — by emitting each commit as a
**second document type** (`doc_type: "commit"`) inside the **same collection**
as the code. Commit documents share one index and one create/update lifecycle
with code chunks; their embedding is the natural-language commit message + diff,
and they cross-link to the code they touched via commit hash. Reading is
**local git only** (`git log` + `git show`); no network, no GitHub API.

**Parent:** [../../product.md](../../product.md) / **Architecture:** [tech.md](tech.md) / **Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | The `commit` document type living inside the existing code collection; the local commit reader (`git log` + diff via `git show`/`-p`); the commit↔code cross-link keyed on commit hash (`touched_paths` on commit docs); type-aware result formatting that renders a commit hit distinctly from a code hit; one unified create/update lifecycle covering both doc types. |
| **Does not own** | The merged-index / heterogeneous-graph engine foundation — *Merged Collection Graphs (powered by LlamaIndex)*, GitHub issue https://github.com/LennardZuendorf/indexed/issues/148 — this feature **depends on** it, does not build it; the `touching_commits` blame field on code chunks (the *git-metadata-enrichment* feature provides the code side of the cross-link); per-branch index storage (the *branch-aware-collections* feature); re-ranking (issue https://github.com/LennardZuendorf/indexed/issues/144); PR / GitHub-API ingestion (deferred — requires network, breaks the local-first default). |

---

## Requirements

### Requirement: Commit history MUST be indexed as `commit` documents in the same collection as code

When indexing a git-repository source, the files connector MUST emit one
document per commit with `doc_type: "commit"` into the **same** collection that
holds the code documents — one index, no separate collection, no separate
connector. The embedding text MUST be the commit's natural-language message
plus its diff; code chunks MUST NOT receive any git text in their vectors.

#### Scenario: Commits become searchable documents alongside code
- **Given** a collection created from a local git repository
- **When** indexing runs to completion
- **Then** the collection contains both `doc_type: "code"` and `doc_type: "commit"` documents in one shared FAISS index
- **And** a code document's embedding text contains no commit message or diff text

#### Scenario: Non-git source emits no commit documents
- **Given** a source directory that is not a git repository
- **When** indexing runs
- **Then** only `doc_type: "code"` documents are produced and indexing succeeds unchanged

### Requirement: Commit documents SHALL cross-link to the code they touched via commit hash

Each commit document SHALL carry `touched_paths` (and, later, `touched_symbols`)
derived from its diff. The commit hash is the **join key**: commit documents
point outward via `touched_paths`, and code chunks point back via
`touching_commits` (supplied by the *git-metadata-enrichment* feature). This
feature owns only the commit-document side of the link.

#### Scenario: A commit document records the files it changed
- **Given** a commit that modified `packages/utils/retry.py` and `tests/test_retry.py`
- **When** the commit document is built
- **Then** its `touched_paths` lists both relative paths
- **And** its `id` encodes the commit hash so the code side can resolve the link

### Requirement: Search SHALL return both document types and the formatter MUST distinguish commit hits from code hits

A query SHALL match across both `code` and `commit` documents in the shared
index, and the result formatter MUST render a commit hit distinctly — surfacing
hash, author, date, subject, and `touched_paths` — rather than as an anonymous
text chunk.

#### Scenario: A why-question surfaces the responsible commit
- **Given** an indexed collection where retry logic was added in one commit
- **When** the user searches "why was retry logic added"
- **Then** the results include that commit document
- **And** it renders as a commit (hash, author, date, subject, touched paths), visually distinct from code hits

### Requirement: Both document types MUST share one unified create/update lifecycle

A single `index create` / `index update` run MUST produce and refresh both code
and commit documents; there MUST NOT be a second collection or a second command
to keep history in sync. An update MUST ingest only commits newer than the last
indexed commit recorded in the existing change-tracking state.

#### Scenario: One update refreshes both code and history incrementally
- **Given** an existing collection and three new commits since the last run
- **When** `index update` runs once
- **Then** the three new commit documents are added and changed code is re-indexed in the same operation
- **And** no separate command or collection is involved

## Non-Goals

- Building the merged-index / graph engine (issue #148) — depended upon, not owned.
- Ingesting GitHub Pull Requests or any network-sourced history (deferred; would break local-first).
- Re-ranking or blending commit-vs-code scores (issue #144).

## Open Questions

These are undecided **pending the Merged Collection Graphs work (issue #148)**:

- Exactly how `doc_type` is represented and persisted (discriminator field vs. typed node) is defined by #148; this feature consumes whatever #148 lands.
- Whether the commit↔code cross-link is materialized as graph edges or as plain fields on documents — #148 decides; `touched_paths` is written as a field for now.
- How type-aware retrieval is exposed (filter, weighting, or unified rank) — gated on #148's retrieval API.
- Deferred (network, out of scope): PR / GitHub-API ingestion — revisit only if a non-default networked mode is ever introduced.
