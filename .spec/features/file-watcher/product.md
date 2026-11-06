---
type: feature-product
feature: file-watcher
sibling: tech.md
parent: ../../product.md
updated: 2026-11-03
---

# Feature: File Watcher — Product

Keeps **one** named collection fresh while you work: `indexed index watch
<collection>` polls the collection's source tree and runs the normal
incremental update once a burst of edits goes quiet, so search results follow
the files without a manual `index update`.

Resolves [issue #67](https://github.com/LennardZuendorf/indexed/issues/67) — the
file-watching half. Git-hook triggered reindexing stays out of scope (the issue's
own refinement asks for it to be an explicit scope decision, not a bundle).

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Outcome

Editing, adding or deleting a file in a watched collection changes what search
returns — no extra command. A burst (save-all, `git checkout`, formatter run)
costs **one** update, not one per file.

## Enable / disable

- **Enable:** run `indexed index watch <collection>`. That is the only way the
  watcher starts.
- **Disable:** stop the command (Ctrl-C). Nothing is left running.
- **No daemon, no autostart, no config switch.** There is deliberately no
  `[watch] enabled` key: a switch that must be turned on to activate an
  already-explicit command is a second way to be confused. Opt-in *is* the
  command; the issue's "opt-in/default policy must be explicitly decided" is
  decided here.
- Cadence is tunable: `--debounce`/`--poll-interval` flags, or `[watch]
  debounce_seconds` / `poll_interval_seconds` (default 2.0s each).

## Failure behaviour (documented, not incidental)

- **The watched source path disappears** (unmounted drive, renamed directory,
  deleted folder): the loop logs an error once, **keeps the last good index**,
  and keeps polling. It resumes when the path returns. It never runs an update
  against a missing path, because that reads as "every file was deleted" and
  would empty the collection.
- **The update itself fails** (permissions, a collection removed underneath,
  a broken writer): the failure is logged and retried on the next change; three
  consecutive failures end the command with exit code 1 instead of a crash loop.
- **The collection is not a `localFiles` source** (Jira/Confluence/Outline/
  GitHub): refused at startup with exit code 2 — there is no local tree to poll.
- **Two writers at once** (watcher + a manual `index update`): the store has no
  lock; the watcher is single-writer by contract. Documented in [tech.md](tech.md).

## Non-goals

- Git-hook driven reindexing, background services, systemd units.
- Watching *all* collections at once, or collections created after startup.
- Watching remote connectors (they have no local change signal).
- Inotify-level latency: the poll interval is the latency floor.
