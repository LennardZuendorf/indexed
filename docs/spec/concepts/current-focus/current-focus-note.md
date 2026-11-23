---
type: concept
updated: 2026-11-22
---

# Current Focus: Note

**Note (supersedes earlier wording):** the v2 rewrite ships behind the *same
facade names* but over a **new version-marked on-disk format** — the "same
on-disk format" drop-in premise was superseded by core-v2 ADR-1 (v2's goals —
pluggable stores, deletes/filters — cannot be expressed in the v1 format;
core-v2 ADR-1, git history / PR #158). The v1 format stays frozen and fully supported.

**Non-gating deferral (Feature 14):** the indexer factory/registry + multi-indexer
plumbing were NOT deleted — the audit's "phantom generality" premise was wrong
post-Foundation: they are the live embedding-model resolver (3 models) bound to the
on-disk `manifest.indexers[]` byte-stable contract; deleting them would inline
duplicated construction at four call sites and risk collection-load compatibility.
Left as a documented follow-up for the v2 rewrite (see Decision Log 2026-07-10).
