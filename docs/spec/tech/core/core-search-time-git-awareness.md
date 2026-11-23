---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Search-Time Git Awareness (v2, issues #60/#144/#146)

Four opt-in options on `core.v2.retrieval.search` — query-time only: no new persisted
state, no re-index, and the v1 engine ignores all of them (its behaviour is unchanged).

| Option | Effect |
|--------|--------|
| `changed_since: str` | Keep only result documents whose file changed since that git ref, **including uncommitted and untracked work**. Applied to retrieved nodes after the cosine threshold and before Git and cross-encoder reranking, so `top_n` and `max_docs` fill with eligible survivors. |
| `git_provenance: bool` | Attach a document-level `git` field — `{commit, short, author, email, committedAt, subject}` (camelCase, additive: absent when not requested). |
| `git_line_blame: bool` | Attach a **per-chunk** `git` field on each `matchedChunks` entry whose chunk recorded a line span — the commit that last touched THOSE lines, plus `startLine`/`endLine` (1-based, inclusive). Independent of `git_provenance`; absent when git or blame cannot answer. |
| `git_rerank: GitRerankOptions \| None` | **Re-rank** the candidates by git recency / churn / ownership before grouping, blending those signals into the score (`scoreKind` becomes `git-rerank`). `None` (default) does no git work at all. |

All four are no-ops unless the collection's manifest reader is a files reader
(`localFiles`/`files` **and** a `basePath`); the repo is resolved ONCE per collection
via `utils/git_meta.repo_toplevel` (see [tech-connectors](../connectors/README.md) § Query-Time
Git Helper), node `source_id`s are rebased from base-path-relative to repo-relative, and
a git failure (not a repo, invalid ref, no history) skips the option — never an empty
result set and never a raised search. Provenance costs at most one
`git log -1` per admitted document, memoized per `(repo, path)` within the call.

**Line-level granularity (`git_line_blame`).** A chunk is attributed only when its
parser recorded the span it came from — `start_line`/`end_line` (0-based, inclusive) in
the node metadata, which today means the code chunker's chunks
(`parsing/code_chunker.py`). Everything else (Docling PDF/DOCX chunks, plaintext
chunks) has no line mapping, so it gets NO line-level field rather than the file's
whole-file commit wearing a line-level label. The cost is ONE
`git blame --line-porcelain` per path per collection per search — memoized in
`_GitContext.blames`, so a multi-chunk document pays a single blame — with each call
bounded by the helper's 5 s timeout. The bound is therefore
`min(admitted documents, max_docs)` blame invocations per collection per search
(default `max_docs` = 10), never `max_docs × chunks`.

Within a span, the commit whose author date is newest is the last touch; equal
timestamps resolve to the later line, so the answer is deterministic. A span
containing a working-tree line yields `{"uncommitted": true, "startLine", "endLine"}`
instead of a commit — the honest answer is that the lines are not committed yet.
Untracked paths, binary files (a NUL in git's own 8 kB sniff window), out-of-range
spans (the file shrank after indexing) and blame failures all leave the field absent.
The field is additive and separate from `entry["git"]`: line-level does not imply
document-level, and vice versa.
