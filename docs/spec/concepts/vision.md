---
type: concept
updated: 2026-11-22
---

# Vision

A single semantic index over one source is easy — every RAG toolkit does that. What's
hard, and what indexed is *for*, is that no one source has all the answers. Code alone
doesn't explain why a decision was made; a Jira ticket alone doesn't show what shipped;
git history alone doesn't say whether it's still true today.

**Shipped today:** indexed connects to files, Jira, Confluence, Outline, and GitHub, and
indexes each as its own searchable collection ([Areas](../areas/README.md)) — parallel semantic
indexes, queried together or one at a time.

**Where this is going:** one merged knowledge graph per project — repo, docs, issues, git
history, connected codebases, and accumulated lessons/memory tied together as one
structure, not five indexes you have to query separately. Structural relationships
first (a PR closing an issue, a file importing another file, a commit touching a path),
graph-aware retrieval on top (follow a hit to what it's linked to, not just its nearest
neighbors), then optional local-model-driven merging across sources. This generalizes
past code — the same graph shape works for a second brain, a documentation set, or any
knowledge base that's really several sources pretending to be one. See
[Decision Log](../decisions/README.md) (2026-07-18) for the seam this was designed against
(Core v2's pluggable store) and [Areas](../areas/README.md) for what's shipped vs. planned.
