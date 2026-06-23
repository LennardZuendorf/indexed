---
type: feature-plan
feature: git-history-documents
sibling: tech.md
parent: ../../plan.md
updated: 2026-06-23
---

# Feature: Git History Documents — Implementation Plan

Add commit history as a second document type (`doc_type: "commit"`) inside the
existing code collection: a local git reader + converter feeding the existing
files connector, the creator/searcher carrying `doc_type` through one shared
index, and type-aware formatting. Built test-first, in dependency order.

**Parent:** [../../plan.md](../../plan.md) / **Requirements:** [product.md](product.md) / **Architecture:** [tech.md](tech.md)

**Feature gate:** This feature MUST NOT start until **Merged Collection Graphs
(powered by LlamaIndex)** — GitHub issue
https://github.com/LennardZuendorf/indexed/issues/148 — has landed the
heterogeneous-document / `doc_type` engine foundation. It also relies on the
*git-metadata-enrichment* feature for the code-side `touching_commits` half of
the cross-link. Implementation begins only after #148 merges.

---

## Problem Frame

Code says *what*; history says *why*. We want "find the commit that introduced
retry logic" answerable from the same collection as the code. The architectural
decision is fixed: **one collection, one index, one lifecycle**, commits as a
second document type — not a standalone connector or a separate collection
(rejected: doesn't stand alone, second lifecycle, cross-store drift). Reading is
local git only; PR/GitHub ingestion is out of scope (network).

## Requirements Trace

| Requirement | Units |
|-------------|-------|
| R1 — commit docs in same collection, no vector pollution | git-history-documents/1, git-history-documents/2, git-history-documents/4 |
| R2 — commit↔code cross-link via hash (`touched_paths`) | git-history-documents/2 |
| R3 — search returns both types; formatter distinguishes | git-history-documents/5, git-history-documents/6 |
| R4 — single unified create/update lifecycle | git-history-documents/3, git-history-documents/4 |

## Key Technical Decisions

- **Second document type, not a second collection/connector.** Commits ride the
  existing files connector and FAISS index. (R1, R4)
- **Local git only.** `git log` + `git show -p` via subprocess, mirroring the
  existing `ChangeTracker` git strategy. No network; PR ingestion deferred.
- **`doc_type` is a plain field for now.** The canonical discriminator and any
  graph edges are owned by issue #148; consume what it provides.
- **Cross-link by hash.** Commit docs own `touched_paths`; code chunks' reverse
  `touching_commits` comes from *git-metadata-enrichment*. (R2)
- **No vector pollution.** Code chunk `indexedData` is untouched; commit docs are
  separate documents whose embedding is the message+diff. (R1)

---

### git-history-documents/1 — Local commit reader

**Goal:** Read commits from a local git repo as plain dicts (metadata + diff +
touched paths), incrementally from a `since_commit` watermark.
**Requirements:** R1
**Dependencies:** —
**Files:** `packages/indexed-connectors/src/connectors/files/commit_reader.py` (new); `tests/unit/indexed_connectors/files/test_commit_reader.py` (new)
**Test scenarios:**
- `is_git_repo` true for a fixture git repo, false for a plain dir.
- `read_all_commits()` yields one dict per commit with hash/author/date/subject/body/diff/touchedPaths.
- `since_commit` set → only commits in `since..HEAD` are yielded.
- Non-git path → empty iterator, no exception.
**Verification:** `uv run pytest tests/unit/indexed_connectors/files/test_commit_reader.py -q`; `uv run mypy src/`.

### git-history-documents/2 — Commit converter (doc_type + touched_paths)

**Goal:** Map a commit dict to the existing on-disk document shape with
`doc_type: "commit"`, `id = commit:<hash>`, `touched_paths`, message-first text
and chunks.
**Requirements:** R1, R2
**Dependencies:** git-history-documents/1
**Files:** `packages/indexed-connectors/src/connectors/files/commit_converter.py` (new); `tests/unit/indexed_connectors/files/test_commit_converter.py` (new)
**Test scenarios:**
- Converts a commit dict to one document with `doc_type == "commit"` and `id == "commit:<hash>"`.
- `touched_paths` equals the diff's changed relative paths.
- `text`/first chunk lead with subject+body (message-first); no code-chunk shape leaks in.
**Verification:** `uv run pytest tests/unit/indexed_connectors/files/test_commit_converter.py -q`; `uv run mypy src/`.

### git-history-documents/3 — Connector emits commit docs in one lifecycle

**Goal:** `FileSystemConnector` yields commit documents alongside file documents
when the source is a git repo and the commit-history flag is on, using the
`last_indexed_commit` watermark for incremental updates.
**Requirements:** R4
**Dependencies:** git-history-documents/1, git-history-documents/2
**Files:** `packages/indexed-connectors/src/connectors/files/connector.py` (edit); `packages/indexed-connectors/src/connectors/files/schema.py` (edit); `packages/indexed-connectors/src/connectors/files/change_tracker.py` (edit); `tests/unit/indexed_connectors/files/test_connector_commits.py` (new)
**Test scenarios:**
- Git source with flag on → output stream contains both file docs and commit docs.
- Non-git source → no commit docs, behavior unchanged.
- Update run passes `last_indexed_commit` so only new commits are emitted; watermark advances.
**Verification:** `uv run pytest tests/unit/indexed_connectors/files/ -q`; `uv run mypy src/`.

### git-history-documents/4 — Creator persists doc_type through one index

**Goal:** The creator writes/reads `doc_type` per document and indexes both
types into the single FAISS index in one create/update run (consuming the #148
foundation).
**Requirements:** R1, R4
**Dependencies:** git-history-documents/3
**Files:** `packages/indexed-core/src/core/v1/engine/core/documents_collection_creator.py` (edit); `tests/unit/indexed_core/test_creator_doc_types.py` (new)
**Test scenarios:**
- Mixed create → `documents/*.json` carry `doc_type`; one `index.faiss` holds both types.
- Code documents persisted with no commit text in any `indexedData`.
- Update adds new commit docs and re-indexes changed code in a single run.
**Verification:** `uv run pytest tests/unit/indexed_core/ -q --cov=src`; `uv run mypy src/`.

### git-history-documents/5 — Searcher returns both types with commit metadata

**Goal:** Search the shared index across both types; each result carries
`doc_type` and, for commit hits, commit metadata (hash/author/date/subject/
touched paths).
**Requirements:** R3
**Dependencies:** git-history-documents/4
**Files:** `packages/indexed-core/src/core/v1/engine/core/documents_collection_searcher.py` (edit); `tests/unit/indexed_core/test_searcher_doc_types.py` (new)
**Test scenarios:**
- Query over a mixed collection returns both code and commit results.
- Commit result includes `doc_type == "commit"` and a populated `commit` block.
- Code result includes `doc_type == "code"` and `commit is None`.
**Verification:** `uv run pytest tests/unit/indexed_core/ -q -k search --cov=src`; `uv run mypy src/`.

### git-history-documents/6 — Type-aware formatting (CLI + MCP)

**Goal:** CLI and MCP formatters render commit hits distinctly (hash, author,
date, subject, touched paths); code hits render unchanged.
**Requirements:** R3
**Dependencies:** git-history-documents/5
**Files:** `apps/indexed/src/indexed/knowledge/commands/search.py` (edit); `apps/indexed/src/indexed/mcp/formatting.py` (edit); `tests/unit/indexed_app/test_commit_formatting.py` (new)
**Test scenarios:**
- A commit result renders with hash/author/date/subject/touched-paths.
- A code result renders in its existing form.
- Mixed result set renders both distinctly in json/table/cards and MCP output.
**Verification:** `uv run pytest tests/unit/indexed_app/ -q`; full gate: `uv run ruff check . --fix && uv run ruff format && uv run mypy src/ && uv run pytest -q --cov=src`.
