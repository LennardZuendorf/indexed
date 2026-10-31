# Issue #126: interrupted collection replacement

This sanitized fixture summarizes the public issue's current PM refinement.
It is fixture evidence, not a live GitHub connector check.

## Outcome and rationale

A failed build must preserve the prior readable collection. A process interruption
during publication must not leave complete data permanently invisible.
The historical delete-before-persist recipe is obsolete: the implementation now
builds aside and swaps directories. The remaining gap was recovery after interruption.

## Failure window

Collection replacement renames the old canonical directory to a trash sibling,
then renames the completed staging directory to the canonical name. A process can
die between those renames. Recovery must identify preserved complete generations
and restore one canonical collection before normal discovery or search.

## Constraints

Do not mix generations. An interrupted new build must not appear healthy.
Use the supported local filesystem and one-writer assumption. Residual backups
must not be deleted without proving that they are redundant. Migration's
`.v1-backup` retention is a separate contract from swap trash cleanup.

Rename-based process-crash recovery does not prove power-loss durability.
There is no fsync design here, so the fixture does not promise survival of an
unflushed power cut or a universal no-gap atomic publication contract.

