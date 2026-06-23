---
type: feature-plan
feature: git-metadata-enrichment
sibling: tech.md
parent: ../../plan.md
updated: 2026-06-23
---

# Feature: Git Metadata Enrichment — Implementation Plan

Build a `BlameEnricher` in the files connector, wire it into the reader so code
chunks gain git metadata, thread those fields through persistence (document JSON
+ `index_document_mapping.json`) and search results, and add a `content_hash`
blame cache plus graceful non-git/uncommitted handling — all without touching
the embedded text. Test-first per the connectors spec; mock git output, let
parsing run on small fixtures.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** foundational — can start now; it is the keystone the
blame-ownership feature and issues
[#144](https://github.com/LennardZuendorf/indexed/issues/144) /
[#147](https://github.com/LennardZuendorf/indexed/issues/147) depend on.

## Problem Frame

Code chunks already carry `start_line`, `end_line`, `file_path`, `language`,
`node_type`, and a `content_hash` (see `code_chunker.py` `_make_chunk` and
`schema.py` `ParsedChunk`). `git blame -L start,end --porcelain -C -M` over that
range yields the touching commits. Git access is only allowed in the connector
layer; `change_tracker.py` already detects the repo and translates base-path ↔
repo-toplevel paths, so blame reuses that logic. The hard constraint: git facts
are sidecar metadata for filter/display/rerank and must never enter
`contextualized_text` or the embedding.

## Requirements Trace

| Requirement | Units |
|-------------|-------|
| R1 — capture per-chunk blame at index time | git-metadata-enrichment/1, git-metadata-enrichment/2 |
| R2 — persist git metadata, keep vector pure | git-metadata-enrichment/2, git-metadata-enrichment/3 |
| R3 — return git metadata in search results | git-metadata-enrichment/4 |
| R4 — cache by content_hash, incremental, graceful | git-metadata-enrichment/1, git-metadata-enrichment/2 |

## Key Technical Decisions

- **Blame lives in the connector.** Core/parsing must not import git; the new
  `BlameEnricher` sits beside `change_tracker.py` and reuses its repo detection
  and `_git_path_to_rel` translation.
- **`-C -M` for rename survival**; `--porcelain` for stable parsing.
- **Cache key = chunk `content_hash`** (the branch-aware-reuse hash). Identical
  function bytes ⇒ reuse blame; update-time only blames ChangeTracker-delta files.
- **Vector purity is a test, not a comment.** A unit asserts
  `contextualized_text` is byte-identical pre/post enrichment.
- **Core stays git-agnostic** — it copies opaque metadata keys through the
  mapping and search result, gaining no git knowledge.

### git-metadata-enrichment/1 — BlameEnricher: line-range blame + cache + graceful no-op

**Goal:** Standalone class that turns (file, line range, content_hash) into a
`GitChunkMeta`, with repo detection, porcelain parsing, `-C -M`, uncommitted
handling, and a `content_hash` cache. Returns `None` outside a git tree or on
failure.

**Requirements:** R1, R4
**Dependencies:** —
**Files:** `packages/indexed-connectors/src/connectors/files/blame_enricher.py`
(new); reuse `change_tracker.py` `_git_toplevel` / `_git_path_to_rel`.
**Test scenarios:**
- Committed range → fields populated; `last_commit`/`commit_count`/dates correct.
- Renamed file → pre-rename commit present in `touching_commits` (`-C -M`).
- Zero-sha hunk → `uncommitted=True`, zero sha excluded from `touching_commits`.
- Non-git `base_path` → `available is False`, `enrich(...) is None`.
- Blame subprocess error/timeout → `None`, no exception raised.
- Second `enrich` with same `content_hash` → no subprocess call (cache hit).
- 0-based chunk rows converted to 1-based `-L` args.
**Verification:** `uv run pytest tests/unit/indexed_connectors/files/test_blame_enricher.py -q`;
`uv run mypy src/`.

### git-metadata-enrichment/2 — Wire enricher into the files reader (keep vector pure)

**Goal:** Instantiate `BlameEnricher` in `FilesDocumentReader`, and after each
`ParsedDocument` is produced, merge `GitChunkMeta.as_metadata()` into each code
chunk's `metadata` (in place). Never modify `contextualized_text`. Honor the
existing `specific_files` delta path so updates only blame changed files.

**Goal cont.:** Skip non-code chunks and chunks missing line numbers.

**Requirements:** R1, R2, R4
**Dependencies:** git-metadata-enrichment/1
**Files:** `packages/indexed-connectors/src/connectors/files/files_document_reader.py`
(edit); `packages/indexed-connectors/src/connectors/files/v1_adapter.py` (verify
`ch.metadata` already flows through `reader_output`/`converter_output`).
**Test scenarios:**
- Git fixture repo → code chunks carry git keys in `metadata`.
- `contextualized_text` byte-identical with vs without enrichment (R2 purity).
- Non-git source → chunks unchanged, indexing succeeds.
- `specific_files` set → only those files are blamed.
**Verification:** `uv run pytest tests/unit/indexed_connectors/files/ -q`;
confirm purity assertion passes.

### git-metadata-enrichment/3 — Persist git fields into index_document_mapping

**Goal:** In `documents_collection_creator.py`, when building
`index_mapping[last_index_item_id]`, copy the chunk's git metadata sub-object so
provenance is available without loading the full document. Keep core git-agnostic
(copy known keys, no parsing).

**Requirements:** R2
**Dependencies:** git-metadata-enrichment/2
**Files:** `packages/indexed-core/src/core/v1/engine/core/documents_collection_creator.py`
(edit `__add_documents_to_index`).
**Test scenarios:**
- Indexed git collection → `index_document_mapping.json[<id>]` has a `git`
  sub-object with the expected keys.
- Chunk without git metadata → mapping entry omits `git` (no crash, no null
  pollution).
**Verification:** `uv run pytest tests/unit/indexed_core/ -q -k mapping`;
`uv run mypy src/`.

### git-metadata-enrichment/4 — Return git fields in search results

**Goal:** In `documents_collection_searcher.py` `__build_chunk_result`, include
the chunk's git fields (from the mapping) in each `matchedChunks` entry when
present.

**Requirements:** R3
**Dependencies:** git-metadata-enrichment/3
**Files:** `packages/indexed-core/src/core/v1/engine/core/documents_collection_searcher.py`
(edit `__build_chunk_result`).
**Test scenarios:**
- Query matching an enriched chunk → result `matchedChunks[].git` present.
- Query matching a non-git chunk → no `git` key, result shape otherwise
  unchanged.
**Verification:** `uv run pytest tests/unit/indexed_core/ -q -k search`; full
gate: `uv run ruff check . --fix && uv run ruff format`, `uv run mypy src/`,
`uv run pytest -q --cov=src`.
