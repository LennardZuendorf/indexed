---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Collection replace + interrupted-swap recovery (#126)

**Files:** `src/indexed/core/v2/persist.py` (`replace_dir`),
`src/indexed/core/v2/ingestion.py` (create/update call sites),
`src/indexed/core/recovery.py`, `src/indexed/core/engine.py` (`_recover` gates).

A collection is never mutated in place: the new generation is built beside the
live directory and swapped in with two renames — `rename(dest -> dest.trash-<pid>)`
then `rename(<name>.tmp-<pid>-<hex> -> dest)` — after which the trash is removed.
A failure of the second rename renames the original back and re-raises.

The remaining window is a CRASH between those two renames: the canonical path is
missing while both generations sit in directories discovery excludes
(`\.(?:tmp|trash)-\d+`). `core.recovery.recover_stranded` therefore runs inside
every list/open gate (`_existing_collection_names`, `_resolve_existing_engine`,
`_group_names_by_engine`, `discover_v2_collections`) and:

- restores the newest COMPLETE generation (readable `version: "2"` manifest plus
  all three `storage/*.json` files) to the canonical name when a `.trash-`
  sibling proves the swap was in flight;
- never promotes a `.tmp-`-only strand (an interrupted new build was never
  published) and never mixes two generations;
- quarantines anything it cannot prove restorable into `<collections>/.recovery/<name>/`
  — moved, never deleted — with a `recovery.log`, and writes the durable
  `quarantine.json` marker ONLY for a name whose data it actually moved there: a
  hold on a live writer, or an incomplete canonical left in place, gets no marker
  (an empty `.recovery/<name>/` must not claim preserved data) and its
  `CollectionRecoveryError` names the canonical directory instead;
- removes a `.trash-` sibling only when the canonical directory is already
  complete (finishing the interrupted cleanup);
- touches a strand ONLY when its writer is proven finished, because the pid in
  the name is the only ownership record: a strand carrying the CURRENT process's
  pid is an in-flight write of ours (a long-lived MCP server runs searches while
  it creates/updates) and is never swept; a pid that is alive is left alone and,
  when the collection has no readable directory, the hold is RECORDED so it does
  not read as "no such collection" (a recycled pid never finishes); on non-POSIX
  platforms liveness is unknowable (`os.kill` is `TerminateProcess` on Windows,
  so probing would kill the recorded process) and nothing is swept;
- raises `CollectionRecoveryError` for an EXPLICITLY requested collection that
  could not be restored, and keeps the explanation ALIVE across reads: the
  quarantining pass is one-shot, so the reason is also read back from the
  `quarantine.json` marker on every read path — an unfiltered search returns a
  per-collection `{"error": …}` entry (never a bare "No results found") and a
  sweep logs it — until the collection is readable at its canonical name again.

**Contract:** recoverable after a process crash between the renames. NOT
power-loss safe — there is no `fsync` in the rename chain, so unflushed pages
after a power cut are outside this guarantee.
