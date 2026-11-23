---
type: concept
updated: 2026-11-23
---

# Git and Development Sources (M3)

[GitHub milestone 13](https://github.com/LennardZuendorf/indexed/milestone/13) · [Parent issue #342](https://github.com/LennardZuendorf/indexed/issues/342) · [Readiness](README.md)

A developer can search Git history as evidence for why code changed and distinguish a historical match from the current source tree.

| Requirement | Observable behavior |
| --- | --- |
| Current and historical evidence | Search current checkouts, commit messages and authors, changed paths and bounded diff evidence. Each historical result identifies the originating repository and commit. |
| Change scope | Limit search to a ref range or a PR's changes. An unresolved ref or unavailable comparison range has an explicit outcome. |
| Source lifecycle | Index a local checkout or remote Git repository. Report what changed, which revisions were indexed, and whether updates succeeded. Surface shallow history and collection limits as partial coverage. |
| Revision navigation | Opening a result reaches the cited revision, or reports why that revision is unavailable. Renames and deleted paths retain their historical context. |

**Acceptance.** Find why a file changed and open the cited commit and changed range from both a checkout and a remote Git source. Cover a branch switch, shallow or detached history, a rewritten ref, a rename, a deletion and an unavailable remote. Demonstrate that results and freshness describe the actual indexed snapshot after each case.

The Git source design settles commit selection, initial history and diff bounds, and remote refresh policy. Historical repository snapshots are tracked separately in [#147](https://github.com/LennardZuendorf/indexed/issues/147).

Issues: [#60 Git and code awareness](https://github.com/LennardZuendorf/indexed/issues/60) · [#92 remote Git](https://github.com/LennardZuendorf/indexed/issues/92) · [#145 ref and PR scope](https://github.com/LennardZuendorf/indexed/issues/145) · [#146 freshness](https://github.com/LennardZuendorf/indexed/issues/146). [#355 Git history ingestion](https://github.com/LennardZuendorf/indexed/issues/355) owns searchable commit and diff evidence.
