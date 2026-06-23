---
type: feature-product
feature: git-metadata-enrichment
sibling: tech.md
parent: ../../product.md
updated: 2026-06-23
---

# Feature: Git Metadata Enrichment — Product

Code chunks indexed today carry zero git provenance, so search results cannot
answer who last touched a function, when, or how often it has changed. This
feature derives per-chunk git facts from `git blame` over each chunk's line
range and attaches them as structured **sidecar metadata** on existing code
chunks — surfaced for filtering, display, and downstream re-ranking. Git facts
are metadata only: they MUST NOT be folded into the embedded text, or semantic
similarity degrades. This is the foundation that blame/ownership and time-travel
search build on.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| Owns | Does not own |
|------|--------------|
| Blame capture in the files connector (line-range → commits) | Re-ranking by recency/authorship ([#144](https://github.com/LennardZuendorf/indexed/issues/144)) |
| Git fields on code chunks, document JSON, and `index_document_mapping.json` | The `who_owns` MCP tool and ownership display (blame-ownership feature — it consumes this data) |
| Git fields returned in search results (`matchedChunks`) | Commit-as-document indexing (git-history-documents feature) |
| Blame cache keyed by chunk `content_hash` + incremental re-blame on update | Branch-scoped collection storage (branch-aware-collections feature) |
| Graceful no-op for non-git sources and uncommitted lines | Embedding model / vector index changes |

---

## Requirements

### Requirement: Capture per-chunk git blame at index time — the connector SHALL run blame over each code chunk's line range

For every code chunk read from a git-tracked file, the files connector shall run
`git blame` over the chunk's `start_line`–`end_line` range and derive the
commits that last touched those lines.

#### Scenario: Code chunk inside a git repository
- **Given** a Python file tracked in a git repository with committed history
- **When** the collection is indexed
- **Then** each code chunk gains git facts: `last_commit`, `last_author`,
  `last_committed_date`, `touching_commits`, `commit_count`, `oldest_line_date`

#### Scenario: Rename and move history is preserved
- **Given** a file (or function) whose lines originated in a now-renamed file
- **When** blame runs with copy/move detection enabled (`-C -M`)
- **Then** the touching commits include the pre-rename history rather than a
  single "file added" commit

### Requirement: Persist git metadata without polluting the embedded vector — git facts MUST stay out of `contextualized_text`

Git facts shall be persisted into chunk metadata in the document JSON and into
`index_document_mapping.json`, but MUST NOT be appended to a chunk's
`contextualized_text` or otherwise included in the text that is embedded.

#### Scenario: Embedded text is unchanged by enrichment
- **Given** a code chunk before and after git enrichment
- **When** the chunk is embedded
- **Then** the embedded `contextualized_text` is byte-identical to the
  un-enriched version (code + path only), while git fields live only in metadata

#### Scenario: Git fields are queryable without loading the full document
- **Given** an indexed collection
- **When** `index_document_mapping.json` is read for a chunk's index id
- **Then** the chunk's git fields are present alongside `documentId`,
  `documentUrl`, `documentPath`, and `chunkNumber`

### Requirement: Return git metadata in search results — the searcher SHALL expose git fields on matched chunks

Search results shall carry each matched chunk's git fields so callers (CLI, MCP,
re-rankers) can display and filter on provenance.

#### Scenario: Matched chunk carries provenance
- **Given** a query that matches a git-enriched code chunk
- **When** the search result is built
- **Then** the chunk entry under `matchedChunks` includes the persisted git
  fields

### Requirement: Cache blame and handle non-git and uncommitted cases gracefully — enrichment SHALL be incremental and MUST NOT fail indexing

Blame results shall be cached keyed by chunk `content_hash` so unchanged
function bytes reuse prior blame; on `index update` only files in the
ChangeTracker delta are re-blamed. Non-git sources, blame failures, and
uncommitted lines MUST degrade to a safe no-op rather than failing the run.

#### Scenario: Unchanged chunk reuses cached blame
- **Given** a previously indexed collection
- **When** `index update` runs and a file's content hash is unchanged
- **Then** no `git blame` is invoked for that chunk and the cached git fields
  are reused

#### Scenario: Non-git source produces no git fields
- **Given** a source directory that is not inside a git working tree
- **When** the collection is indexed
- **Then** indexing succeeds and chunks simply carry no git fields

#### Scenario: Uncommitted working-tree lines
- **Given** a chunk whose lines were edited but not committed (blame sha is all
  zeros)
- **When** blame is interpreted
- **Then** those lines are attributed to the working tree / current user, not to
  a phantom commit

## Non-Goals

- No commit graph traversal, PR linkage, or issue linkage — only blame facts.
- No new CLI flags or config keys; enrichment runs automatically for git repos.
