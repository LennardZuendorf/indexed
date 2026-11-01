# PR #244: recover collections stranded by a crashed swap

This sanitized fixture summarizes the merged public pull request's behavior.
It is fixture evidence, not a live GitHub connector check.

## Why the collection disappeared

The swap already builds aside and can roll back a caught rename failure.
A process death between old-to-trash and staging-to-canonical leaves the canonical
directory absent. Discovery skips `.trash-` and `.tmp-` siblings, so complete
preserved data can become invisible without an explicit recovery pass.

## Implementation and ownership

`recover_stranded` in `src/indexed/core/recovery.py` runs at collection open/list
gates. It restores one complete v2 generation and quarantines other preserved
paths under `.recovery/<name>/`; it never mixes generations.

Only a writer proven finished can be swept. The current process's PID identifies
an in-flight build and is skipped. A live or recycled PID is held and explained.
On non-POSIX systems the process is not probed or swept: signal-zero probing
can terminate the process on Windows.

## Durable explanation

`quarantine.json` records a reason only when the recovery pass actually moved
preserved data. `quarantine_reasons` re-reads this marker on later reads.
An unfiltered search can return a per-collection error instead of an unexplained
empty result. An explicit failed open can raise `CollectionRecoveryError`.
An empty preserved list must not claim data exists in quarantine.

## Limits

This is process-crash recovery, not a power-loss/fsync guarantee.
The v1 persistence implementation and migration backup retention are separate.

