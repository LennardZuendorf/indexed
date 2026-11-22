---
type: tech
updated: 2026-11-22
applies: "docs/spec/**"
---

# Spec Ledger Merging

The mutable `docs/spec/lessons.md` and `docs/spec/tech.md` use normal content merging.
Union merging can silently duplicate frontmatter keys when both sides edit metadata.
Resolve overlapping ledger additions and frontmatter conflicts explicitly.
