---
type: tech
updated: 2026-11-22
applies: src/indexed/utils/git_meta.py
---

# Query-Time Git Helper (`utils/git_meta.py`) (2)

- Stdlib `subprocess` only, every call a list argv with `timeout=5`, a checked return
  code, and **all** exceptions swallowed to `None`/empty: a git problem must never
  break a search. The child env strips leaked `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`/
  `GIT_OBJECT_DIRECTORY`/`GIT_CEILING_DIRECTORIES` and pins `GIT_TERMINAL_PROMPT=0`,
  `LC_ALL=C` — the same hygiene as `change_tracker.py`.
- `repo_toplevel` / `is_git_repo` — `git rev-parse --show-toplevel`.
- `changed_paths(repo, ref)` — union of `git diff --name-only <ref> --` (REF's tree vs
  the **working tree**, so committed, staged and unstaged changes all count) and
  `git ls-files --others --exclude-standard` for untracked work. Two legs: a plain
  `git diff` and a `--cached` diff add nothing this one call does not already see. NUL-delimited paths preserve whitespace and newlines.
  An invalid ref returns `None` (verified up front via
  `rev-parse --verify <ref>^{commit}`) — a typo must never look like "nothing changed".
- `head_commit` / `commit_exists` / `is_ancestor` / `is_shallow_repository` /
  `commit_count` / `is_detached_head` — the freshness facts behind
  `utils/freshness.py` (#146 slice 1): the HEAD SHA, whether the indexed commit still
  exists and is an ancestor of HEAD, a real `rev-list --count`, and detached-HEAD
  detection. These need `_run_code`, because `merge-base --is-ancestor` answers "no"
  with exit 1 — folding that into `None` like `_run` does would turn "git says no" into
  "git is broken", and `unknown`/`history-rewritten` must stay distinguishable.
- `ignored_paths` — `git ls-files --others --ignored --exclude-standard`. `git status`
  never reports an ignored file, so one that was indexed and only later ignored would
  otherwise read `fresh` forever.
- `last_commit(repo, path)` — ONE `git log -1 --format=…` per file, giving
  `{commit, short, author, email, committedAt, subject}`. `committedAt` is the committer time; author time remains the blame recency signal. Line blame is an independent opt-in.
- `snapshot_is_current(base_path, source_id, modified_time, indexed_at=None)` — compares
  a node's indexed `modified_time` with the file's mtime now (`os.path` + `stat`, no
  subprocess). The stored value is offset-aware UTC, so the comparison is
  zone-independent; an offset-less (legacy) value is judged instead against the
  manifest's `updatedTime`, which is zone-free. `last_commit` answers for the file as it
  is on disk, so retrieval attaches provenance only while this says the indexed
  snapshot still describes it.
- `blame_lines(repo, path)` — ONE `git blame --line-porcelain` per file, parsed into
  one record per line (`commit`/`short`/`author`/`email`/`committedAt`/`subject` plus
  the sort-only author epoch). `None` when blame cannot answer: untracked path,
  non-repo, binary file (a NUL in git's own 8 kB sniff window — plain blame would
  return a binary blob as one meaningless "line"), or any git failure. Callers memoize
  by `(repo, path)` within a search, so a document's chunks share one call.
- `resolve_range(lines, start_line, end_line)` — pure mapping from a 0-based inclusive
  span to its newest touching commit (`startLine`/`endLine` are reported 1-based, as
  git counts). A span with any working-tree line returns
  `{"uncommitted": true, "startLine", "endLine"}` — never the committed ancestor
  dressed up as line-level provenance — and a gap or out-of-range span returns `None`.
- `repo_relative(repo, base_path, source_id)` — document ids are base-path-relative
  (`v1_adapter.py:35-36`), git pathspecs are repo-relative; this rebases with `os.path`
  arithmetic only (no symlink resolution, no filesystem probe).
- **No global cache.** Callers memoize per search call, so a long-lived MCP server
  cannot serve stale git facts.
