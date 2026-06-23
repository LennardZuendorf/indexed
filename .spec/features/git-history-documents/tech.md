---
type: feature-tech
feature: git-history-documents
sibling: product.md
parent: ../../tech.md
updated: 2026-06-23
---

# Feature: Git History Documents — Architecture

Commit history is ingested by the **existing files connector** as a second
document type (`doc_type: "commit"`) written into the **same** collection as
code. A new local `CommitReader` runs `git log` + `git show` (subprocess, no
network) and a converter maps each commit to the existing on-disk document
shape (`id`, `url`, `modifiedTime`, `text`, `chunks[]`) extended with
`doc_type` and `touched_paths`. The creator/searcher persist and retrieve both
types from one FAISS index; the searcher returns `doc_type` and the formatter
branches on it. The `doc_type` discriminator, graph cross-linking, and
type-aware retrieval are provided by **Merged Collection Graphs (issue
https://github.com/LennardZuendorf/indexed/issues/148)** — this feature builds
on that foundation and does not reimplement it.

**Parent:** [../../tech.md](../../tech.md) / **Requirements:** [product.md](product.md) / **Plan:** [plan.md](plan.md)

---

## Files

```
packages/indexed-connectors/src/connectors/files/
  commit_reader.py            NEW  local git log+diff reader (subprocess)
  commit_converter.py         NEW  commit dict → v1 document shape + doc_type/touched_paths
  connector.py                EDIT FileSystemConnector emits commit docs when source is a git repo
  change_tracker.py           EDIT expose last_indexed_commit as the commit-ingest watermark (git strategy already tracks it)
  schema.py                   EDIT add index_commits / commit-history config flag

packages/indexed-core/src/core/v1/engine/core/
  documents_collection_creator.py   EDIT persist/read doc_type per document (per issue #148 foundation)
  documents_collection_searcher.py  EDIT carry doc_type + commit metadata into results

apps/indexed/src/indexed/mcp/formatting.py            EDIT render commit hits distinctly
apps/indexed/src/indexed/knowledge/commands/search.py EDIT CLI formatter branch for commit hits

tests/unit/indexed_connectors/files/      commit reader + converter tests (fixture git repo)
tests/unit/indexed_core/                  mixed-type create/search tests
```

## Contract / API

```python
# commit_reader.py — local git only, no network
class CommitReader:
    def __init__(self, base_path: str, since_commit: str | None = None) -> None: ...
    def read_all_commits(self) -> Iterator[dict]: ...
        # each dict: {"hash", "author", "authoredDate", "subject", "body",
        #             "diff", "touchedPaths": list[str]}
    @staticmethod
    def is_git_repo(base_path: str) -> bool: ...   # `.git` present / `git rev-parse`

# commit_converter.py — map to the existing on-disk document shape
class CommitConverter:
    def convert(self, commit: dict) -> list[dict]: ...
        # returns [{
        #   "id": f"commit:{hash}",
        #   "url": f"git://{hash}",
        #   "modifiedTime": authoredDate,        # ISO-8601, reused by creator's time bookkeeping
        #   "doc_type": "commit",
        #   "touched_paths": list[str],
        #   "text": "<subject>\n\n<body>\n\n<diff>",
        #   "chunks": [{"indexedData": "<subject>\n\n<body>"}, ...],  # message-first; diff chunked after
        # }]

# searcher result item gains:
#   {"id", "url", "path", "doc_type": "code"|"commit",
#    "commit": {"hash","author","date","subject","touchedPaths"} | None,  # present iff commit
#    "matchedChunks": [...]}
```

## Implementation Detail

- **Reading (local, no network).** `CommitReader.read_all_commits()` shells out
  with a fixed `--format` to `git log` for metadata, then `git show --format= -p
  <hash>` (or `git log -p`) for the diff. Subprocess invocation mirrors the
  existing `ChangeTracker` git strategy (`subprocess` + `git rev-parse`). When
  `since_commit` is set, the range is `since_commit..HEAD` so updates ingest only
  new commits.
- **Discriminator.** `doc_type` lives on the converted document dict. The
  creator writes it through to `documents/<id>.json` and the searcher's
  index_document_mapping carries enough to recover it (read from the document on
  hit). The canonical representation and any graph edges come from **issue
  #148** — this feature treats `doc_type` as a plain field until #148 lands.
- **No vector pollution.** Code chunks are unchanged: their `indexedData` never
  includes commit text. Commit documents are *separate* documents whose
  embedding legitimately is the message+diff. Same index, different documents —
  no pollution by construction.
- **Cross-link.** Commit docs carry `touched_paths` from the diff (join key =
  bare commit hash inside `id`). The reverse field `touching_commits` on code
  chunks is produced by the *git-metadata-enrichment* feature, not here; both
  sides resolve via the hash.
- **Connector wiring.** `FileSystemConnector` checks `CommitReader.is_git_repo`
  and, when true and the commit-history flag is enabled, yields commit documents
  alongside file documents through the same read→convert→persist path the
  creator already drives. Non-git sources skip the commit reader entirely.
- **Update watermark.** Reuse `IndexState.last_indexed_commit` (already tracked
  by the git change strategy) as `since_commit`; advance it after a successful
  run so re-runs are incremental.
- **Formatting.** Searcher returns `doc_type` (+ commit metadata for commit
  hits); CLI and MCP formatters branch: commit hits render hash/author/date/
  subject/touched-paths; code hits render unchanged.

## Open Questions

- Persisted shape of `doc_type` and whether the cross-link is fields or graph
  edges is owned by issue #148; this design uses plain fields pending that.
- Diff chunking granularity (whole diff vs. per-file hunks) — start with
  message-first single text, revisit once #148's retrieval semantics are known.
