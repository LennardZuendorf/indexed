---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Search-Time Git Awareness (v2, issues #60/#144/#146): Provenance never outlives its snapshot

**Provenance never outlives its snapshot.** `git_provenance` is attached only when the
node's indexed `modified_time` still describes the file at query time
(`utils/git_meta.snapshot_is_current` — a stat comparison, no extra subprocess). If the
file changed or was committed after the collection was indexed, or is dirty relative to HEAD, the `git` field is
omitted rather than crediting a commit that does not contain the returned text;
re-indexing restores it (#279 review, finding 2).

The node timestamp is stored **offset-aware in UTC**
(`datetime.fromtimestamp(mtime, timezone.utc).isoformat()`), so the comparison is
absolute and independent of the querying process's zone or a DST change. An
offset-less value is LEGACY (the old writers stored naive local wall time, whose zone
is unknowable): the guard does not parse it into an instant and instead compares
the file's mtime with the manifest's UTC `updatedTime` — a file not newer than the
index cannot have changed since — which degrades towards *provenance present*
rather than dark. A
node with no timestamp takes the same legacy path; a vanished file always omits the
field. The mtime equality is a heuristic, not a content hash (#279 B1).

A requested **re-rank** that could not run follows the same rule via `gitRerank`:
`{"applied": true, "scored": <n>}` after a run, and
`{"applied": false, "reason": <why>}` when the collection cannot carry it
(`not-a-files-collection`, `no-git-repository`, or `v1-engine`, stamped by the facade),
rendered by `utils/git_meta.rerank_skip_message` as an MCP `collection_errors` entry and
a CLI warning. Rows must never look re-ranked when they are not.

The CLI and MCP accept independent filter, document provenance, line blame and
rerank options. Omitted booleans use `[core.v1.search]` defaults. The grouped
`indexed.search/1` payload places document provenance on `documents[].git`, line
blame on each `hits[].git`, and score semantics on `documents[].score_kind`.
The CLI detail card shows `Last commit` and `Lines commit` when available.

The CLI validates `--changed-since` up front: an unresolvable ref always exits 1, and so
does naming (`--collection`) a collection that cannot carry the filter — no files reader,
no git repo behind it, or the v1 engine. When searching EVERY collection, an unfilterable
one is not fatal (a single Jira collection must not veto the search): it is announced per
collection, exactly like the MCP `collection_errors` entry.
