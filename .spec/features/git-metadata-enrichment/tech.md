---
type: feature-tech
feature: git-metadata-enrichment
sibling: product.md
parent: ../../tech.md
updated: 2026-06-23
---

# Feature: Git Metadata Enrichment — Architecture

Blame runs in the **files connector** (the only layer permitted to shell out to
git; core and parsing MUST NOT import git). A new `BlameEnricher` runs
`git blame -L start,end --porcelain -C -M` per code chunk, reusing the
path-translation logic already in `change_tracker.py`. Derived fields are
attached to chunk metadata via the v1 adapter, copied into
`index_document_mapping.json` by the collection creator, and echoed back by the
searcher. Blame is cached by chunk `content_hash`; `index update` only re-blames
files in the ChangeTracker delta.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

## Files

```
packages/indexed-connectors/src/connectors/files/
  blame_enricher.py        NEW — BlameEnricher: line-range blame → GitChunkMeta, content_hash cache
  files_document_reader.py EDIT — instantiate BlameEnricher; enrich each ParsedChunk's metadata after parse
  v1_adapter.py            EDIT — flow git metadata through reader_output/converter_output (already passes ch.metadata)
  change_tracker.py        REUSE — _git_toplevel / _git_path_to_rel for chunk file → repo path translation
packages/indexed-core/src/core/v1/engine/core/
  documents_collection_creator.py  EDIT — copy chunk git fields into index_mapping[id]
  documents_collection_searcher.py EDIT — include chunk git fields in __build_chunk_result
tests/unit/indexed_connectors/files/test_blame_enricher.py   NEW
tests/unit/indexed_core/                                      EDIT — mapping + search result assertions
```

## Contract / API

```python
# blame_enricher.py
from dataclasses import dataclass, asdict

GIT_META_KEYS = (
    "last_commit", "last_author", "last_committed_date",
    "touching_commits", "commit_count", "oldest_line_date",
)

@dataclass(frozen=True)
class GitChunkMeta:
    last_commit: str            # short sha of most recent touching commit
    last_author: str            # author name of last_commit
    last_committed_date: str    # ISO-8601 committer date of last_commit
    touching_commits: list[str] # unique shas touching the range (recent → old)
    commit_count: int           # len(touching_commits)
    oldest_line_date: str       # ISO-8601 author date of the oldest line
    uncommitted: bool = False   # any line is working-tree (sha 0000…)

    def as_metadata(self) -> dict[str, object]:
        return asdict(self)

class BlameEnricher:
    def __init__(self, base_path: str) -> None: ...

    @property
    def available(self) -> bool:
        """True only when base_path is inside a git working tree."""

    def enrich(self, file_path: str, start_line: int, end_line: int,
               content_hash: str) -> GitChunkMeta | None:
        """Blame [start_line, end_line]; None on non-git / failure.

        Cache hit on content_hash returns prior GitChunkMeta without shelling out.
        """
```

Persistence shape — git fields appear in three places (all derived from the
same `GitChunkMeta.as_metadata()`):

- document JSON `chunks[].metadata.*` (alongside `start_line`, `language`, …)
- `index_document_mapping.json[<index_id>]` — flat `git` sub-object
- search result `matchedChunks[].git` (only when present)

## Implementation Detail

- **Blame command:** `git blame -L <start>,<end> --porcelain -C -M -- <repo_rel_path>`
  run with `cwd=base_path`, `timeout≈30s`, `capture_output=True`. Line numbers
  are 1-based in git; chunk `start_line`/`end_line` are 0-based tree-sitter rows,
  so convert (`start+1`, `end+1`) before passing to `-L`.
- **Path translation:** reuse the `_git_toplevel()` + `_git_path_to_rel()`
  pattern from `change_tracker.py` to map a chunk's absolute file path to a
  repo-root-relative path; do not reinvent it. Factor the shared helper rather
  than copy-paste if practical, otherwise mirror it.
- **Porcelain parsing:** group blame hunks by commit sha header; collect
  `author`, `committer-time`/`committer-tz`, `author-time` per commit. The most
  recent committer-time commit becomes `last_commit`; `oldest_line_date` is the
  min author-time across hunks. Convert epoch+tz to ISO-8601.
- **Uncommitted lines:** a hunk sha of `0000000000000000000000000000000000000000`
  marks working-tree edits — set `uncommitted=True`, attribute author to the
  current `git config user.name` (or "working tree"), and exclude the zero sha
  from `touching_commits`.
- **Caching:** `dict[str, GitChunkMeta]` keyed by chunk `content_hash` (the same
  hash that powers branch-aware reuse). Unchanged function bytes ⇒ identical hash
  ⇒ reuse. Cache is per-`BlameEnricher` instance (per index run).
- **Incremental on update:** the reader already supports `specific_files`; on
  `index update` only files in the ChangeTracker delta are read, so only those
  chunks are blamed. No extra wiring beyond honoring the existing delta path.
- **Enrichment site:** in `read_all_parsed()` / `read_all_documents()`, after a
  `ParsedDocument` is produced, iterate code chunks and merge
  `GitChunkMeta.as_metadata()` into `chunk.metadata`. `ParsedChunk` is frozen,
  but `metadata` is a mutable dict — mutate in place; never touch
  `contextualized_text`.
- **Layering:** all git access stays in the connector. Core only copies opaque
  metadata keys through the mapping and search result; it gains no git knowledge.
- **Non-code chunks:** skip enrichment for `source_type != "code"` and for any
  chunk missing `start_line`/`end_line`.

## Performance Budget

- Blame is the dominant cost. Cap impact via the `content_hash` cache (re-index
  of unchanged code ⇒ ~0 blame calls) and the update-time delta (only changed
  files blamed). One subprocess per (changed) code chunk on first index;
  acceptable for <50k-doc local repos. No blame on non-git sources.

## Open Questions

- Should `last_committed_date` use committer date (chosen, stable across rebases'
  author dates) — confirm with blame-ownership consumer before it ships its UI.
