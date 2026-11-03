---
type: feature-tech
feature: file-watcher
sibling: product.md
parent: ../../tech.md
updated: 2026-11-03
---

# Feature: File Watcher — Architecture

A foreground polling loop in the CLI layer that reuses the existing update path
unchanged. The watcher owns *when*, never *how*: it calls the same
`core.engine.update` the `index update` command calls, so delta detection,
per-document content-hash skip, build-aside staging and the atomic rename swap
all stay in one place.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)
**App spec:** [../../tech-app.md](../../tech-app.md) · **Config:** [../../tech-config.md](../../tech-config.md)

---

## Shape

| Layer | File | Role |
|---|---|---|
| Command | `cli/knowledge/commands/watch.py` | resolve collection + manifest reader config, validate, run the loop |
| Service | `cli/knowledge/commands/watch_service.py` | tree fingerprint, exclusion walk, `run_watch_loop` |
| Config | `cli/watch_config.py` | `[watch] debounce_seconds`, `poll_interval_seconds` |

Registered as `index watch` (plus the flat hidden alias `watch`) in
`cli/_app_setup.py` and `cli/knowledge/cli.py`; the model is registered at
`register_app_config` (path `watch`), never at import time.

## Why polling, not inotify

- No new runtime dependency, so no `uv.lock` churn and no CLI cold-start cost
  (the service module is imported *inside* the command body, mirroring
  `update.py`).
- Works where events do not: network mounts, containers, some CI filesystems.
- The scan is a **wake-up signal only**. A false positive costs one update pass
  that finds no delta and returns a timestamp-only manifest bump — never a
  rebuild. A false negative is the only real risk, which is why the fingerprint
  errs toward over-reporting: include/negation patterns are not mirrored, so a
  file the reader would skip can still wake the loop.

## Fingerprint and burst coalescing

`signature_for(base_path)` returns `(files, blake2b(path,size,mtime_ns over the
sorted watched set))`, or `None` when the base path is not a directory. The walk
prunes the reader's excluded directory names (`DEFAULT_EXCLUDED_DIRS`) and
per-directory `.gitignore` specs, so an edit to an ignored file wakes nothing.

`run_watch_loop` polls, and on a signature change waits for a full quiet
`debounce_seconds` (each further change pushes the deadline out) before running
**one** update. It is fully injectable (`scan`, `apply_update`, `clock`,
`sleep`, `stop`) so the burst/failure semantics are unit-tested without waiting.

## Write contract (must not be broken)

- **Single writer per collection by contract.** There is no lock in the store;
  `replace_dir` publishes atomically, so a second concurrent writer's work is
  silently lost (last swap wins). The watcher never starts a second pass while
  one is running, and it never claims exclusivity it does not have.
- **Never sweep strands.** `.tmp-*`/`.trash-*` siblings belong to
  `core/recovery.py` (`recover_stranded`), which needs pid liveness to decide.
- **A missing canonical directory is transient**, not a deletion: the swap
  window renames the collection dir away before renaming the new one in.
- **The data-loss gate is the feature's spine**: `signature_for` returns `None`
  for a missing base path and the loop refuses to call `update`, because the
  files reader walks a nonexistent path silently (`os.walk` yields nothing),
  which the change tracker would classify as "every file deleted".

## Evidence

- `tests/unit/indexed/knowledge/commands/test_watch.py` — burst coalescing
  (5 changes → 1 update), quiet tree (0 updates), vanished path (0 updates, one
  error, resumes), 3 consecutive failures → exit 1, gitignore/excluded-dir
  fingerprints, `--once`, refusals.
- `tests/system/test_watch_live_edit.py` — real corpus, real files connector,
  real v2 ingestion (embedding mocked): a file written while the loop runs
  becomes a document and is searchable, with no manual `index update`.
