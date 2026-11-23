---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Index Freshness (files collections, #146 slice 1)

Reporting only: how far behind the source working tree a collection's index is. No
hooks, no auto-update, no new persisted state — the baseline already exists.

**Baseline ownership.** The files connector's `state.json` (written by
`ChangeTracker.build_state` in the connector's `post_run`, after a *successful* create or
update) is the one baseline: `last_indexed_commit` + `file_hashes` +
`indexed_file_count`, in the collection directory, v1 and v2 alike. Freshness reads it and
never writes it (`utils/freshness.py::read_baseline`). `utils/freshness.py` holds the
whole verdict; `utils/git_meta.py` supplies every git fact (timeout-bounded, `GIT_*`-scrubbed,
stdlib-only).

**Verdicts and reason codes.** `fresh` / `stale` / `unknown`, one per collection, carrying
a single `summary` line that every surface reuses verbatim (never re-worded downstream).

| Status | Meaning | `reason` |
|--------|---------|----------|
| `fresh` | every source file's current bytes hash to what was indexed | — |
| `stale` | ≥1 source file's bytes differ, or it is gone, or it was never indexed | `source-changed` |
| `unknown` | the question cannot be answered honestly | one of the codes below |

`unknown` reason codes: `not-a-files-collection`, `no-base-path`, `no-git-repository`
(non-git source), `no-head` (unborn HEAD), `no-baseline` (state.json missing/pre-dates
change tracking), `history-missing` (baseline commit absent — shallow/pruned),
`history-rewritten` (baseline exists but is not an ancestor of HEAD), `git-unavailable`.
A degraded answer is NEVER a fabricated `fresh` — the same contract `gitFilter` holds.

**Byte comparison, not just `git status`.** Git can only say "differs from HEAD"; a tree
indexed while dirty is legitimately current. For every changed path inside the source
directory the current bytes are xxhash-compared against `file_hashes` — without stored
hashes the code stays conservative and counts every changed path. Committed changes are
diffed against the baseline commit (ancestry checked first), and `commits_behind` is a real
`rev-list --count`, `None` when git cannot count.

**Conservative on purpose.** The reader's `includePatterns`/`excludedDirs` are NOT
re-applied when counting pending paths: a change to a file the collection never indexed
still reads `stale`. That errs toward a spurious warning, never toward a false `fresh`.

**Surfaces.** `index inspect <name>` gains a `Freshness` row (and a `freshness` object in
`--simple-output`); `indexed index search --freshness` prints one advisory line per
collection (dim when fresh, a warning otherwise); the MCP search tools take
`include_freshness` and the envelope gains a `freshness` list; the MCP collection-status
resources include the verdict. Freshness is attached by the `core.engine` facade, not by
either engine's inspect/status, so v1's engine behaviour is untouched and both engines
report identically. The facade is the only place that resolves manifest reader →
`basePath`, so CLI/MCP cannot drift from it.

**Out of scope (deferred).** `post-commit`/`post-checkout` hooks and an `install-hooks`
command (consolidates with the #67 hook proposals); exact behind-commit counts when
history is missing.
