---
type: concept
updated: 2026-11-22
---

# Knowledge Graph

Direction, not yet shipped — see [Vision](vision.md).

| Feature | Status | Description |
|---------|--------|-------------|
| Structural graph edges | 📋 Planned | Relationships derived from existing source structure — no LLM required (doc→chunk hierarchy, code imports, issue/PR links, commit→file) |
| Graph-aware retrieval | 📋 Planned | Follow a search hit to its linked nodes, alongside vector search — not a replacement for it |
| Cross-source merge | 📋 Planned | Unify multiple collections (code, docs, issues, git history, connected repos, lessons) into one graph per project |
| Local-model-driven merging | 📋 Planned | Optional richer entity/relation extraction via a local model (e.g. Ollama) — additive on top of the structural graph, never required |
