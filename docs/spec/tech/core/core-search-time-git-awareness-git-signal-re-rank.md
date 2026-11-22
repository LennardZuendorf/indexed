---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Search-Time Git Awareness (v2, issues #60/#144/#146): Git-signal re-rank

**Git-signal re-rank (`git_rerank`).** After retrieval and the score threshold, and
BEFORE document grouping (so the groupers see the ranked order), the candidate chunks
are re-scored as
`cosine + w_recency·recency + w_churn·churn + w_author·ownership`:

- **recency** — exponential decay on the chunk's newest touch
  (`0.5 ** (age_days / half_life)`, half-life 30 days), from the chunk's own line span
  via blame, falling back to the document's newest line when the chunk recorded no
  span. A working-tree line counts as fresh (1.0).
- **churn / hotspot** — the document's commit count inside a 90-day window
  (`git rev-list --count --since=<window> HEAD -- <path>`), scaled to 20 commits. One
  call per candidate document, memoized next to the blame.
- **ownership** — `git_rerank_author` (a name/email substring) gives the chunks it last
  touched a fixed bonus. Unset disables ownership entirely.

A signal git cannot answer contributes NOTHING — no fabricated zero-or-one score — and a
chunk with no answerable git at all keeps its cosine value untouched. Only the first 50
candidates are scored (`_GIT_RERANK_WINDOW`); the tail keeps its cosine score and order,
which bounds the cost at one blame + one `rev-list` per distinct candidate document.
The pass never touches the embedding or the vector store and persists nothing, so no
re-index is needed. `scoreKind` becomes `git-rerank` (cosine plus non-negative boosts)
only when at least one candidate was scored. With `[core.v2.rerank]` enabled too, the
git pass runs first and the cross-encoder still owns the final score: it replaces every
blended score, so the git pass only decides which candidates reach the cross-encoder's
`top_n` and the result kind stays `rerank`.

**A skipped filter is never silent.** Every collection result carries a `gitFilter`
status when — and only when — `changed_since` was requested:
`{"ref": <ref>, "applied": true}` after a run, and
`{"ref": <ref>, "applied": false, "reason": <why>}` when it could not run
(`unknown-ref`, `no-git-repository`, `not-a-files-collection`, or `v1-engine` — stamped
by the `core.engine` facade, whose routing is the only place that knows a collection
went to v1). The skip is logged at WARNING, `mcp/formatting.py` turns it into a
`collection_errors` entry naming collection and ref, and the CLI renderers print the
same line via `utils/git_meta.filter_skip_message` — unfiltered rows arriving under a
"changed only" request are a defect, not a quiet degrade.
